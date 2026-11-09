"""Score pretrained AASIST models on our test clips, before any training of our own.

From ml/liveness/, after preprocess.py:

    python score_baseline.py --model asvspoof5=<weights.pth>
    python score_baseline.py --model a=<weights.pth> --model b=<weights.pth> --per-group 500

The weights are public AASIST checkpoints: Baseline-AASIST/models/weights/AASIST/best.pth
in github.com/asvspoof-challenge/asvspoof5 (trained on ASVspoof 5), and
models/weights/AASIST.pth in github.com/clovaai/aasist (trained on ASVspoof
2019 LA). Clone those repos into data/external/, which git ignores. The model
code itself is in models/aasist.py.

The same clips are scored twice: as raw audio (only converted to 16 kHz mono,
which is what the models were trained on) and as preprocessed audio. Comparing
the two shows whether our preprocessing suits a model trained without it.

Writes, in data/baseline/:
- scores.csv: one score per clip, model and audio type. Higher means more
  likely real.
- report.md: equal error rate (EER) by dataset. 0% is perfect, 50% is guessing.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch

import audio
from models.aasist import Model
from validate import DEFAULT_DATA_DIR, markdown_table, read_audio

OUT_FOLDER = "baseline"
BATCH = 32
# The AASIST settings both public checkpoints were trained with.
MODEL_CONFIG = {
    "architecture": "AASIST", "nb_samp": audio.CROP_SAMPLES, "first_conv": 128,
    "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]], "gat_dims": [64, 32],
    "pool_ratios": [0.5, 0.7, 0.5, 0.5], "temperatures": [2.0, 2.0, 100.0, 100.0],
}


def load_model(weights: Path) -> torch.nn.Module:
    """AASIST with a checkpoint's weights. weights_only stops the file running code."""
    model = Model(MODEL_CONFIG)
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    return model.eval()


def read_clip(data_dir: Path, path: str, raw: bool) -> np.ndarray:
    """One clip as AASIST's 4-second input. Raw clips are only made 16 kHz mono."""
    samples, rate = read_audio(data_dir / path)
    clip = audio.to_mono_16k(samples, rate) if raw else samples[:, 0]
    return audio.fix_length(clip)


def score(model: torch.nn.Module, clips: pd.DataFrame, data_dir: Path, raw: bool) -> np.ndarray:
    """The model's 'real' output for each clip, reading the next batch while scoring this one."""
    column = "raw_path" if raw else "path"
    paths = list(clips[column])
    batches = [paths[i : i + BATCH] for i in range(0, len(paths), BATCH)]
    out = []
    with ThreadPoolExecutor(8) as pool, torch.inference_mode():
        read = lambda batch: np.stack([read_clip(data_dir, p, raw) for p in batch])  # noqa: E731
        pending = pool.submit(read, batches[0]) if batches else None
        for n in range(len(batches)):
            x = pending.result()
            if n + 1 < len(batches):
                pending = pool.submit(read, batches[n + 1])
            _, logits = model(torch.from_numpy(x))
            out.append(logits[:, 1].numpy())
            if (n + 1) % 50 == 0:
                print(f"  {(n + 1) * BATCH}/{len(paths)} clips", flush=True)
    return np.concatenate(out) if out else np.array([])


def eer(real: np.ndarray, fake: np.ndarray) -> tuple[float, float]:
    """The error rate where wrongly rejecting real clips equals wrongly accepting
    fakes, and the score threshold where that happens."""
    scores = np.concatenate([real, fake])
    is_real = np.concatenate([np.ones(len(real)), np.zeros(len(fake))])
    order = np.argsort(scores, kind="mergesort")
    scores, is_real = scores[order], is_real[order]
    # With the threshold just above each score: real clips rejected, fakes accepted.
    rejected_real = np.cumsum(is_real) / len(real)
    accepted_fake = 1 - np.cumsum(1 - is_real) / len(fake)
    i = int(np.argmin(np.abs(rejected_real - accepted_fake)))
    return float((rejected_real[i] + accepted_fake[i]) / 2), float(scores[i])


def summarise(scores: pd.DataFrame) -> pd.DataFrame:
    """EER per model, audio type and dataset, plus all datasets pooled.

    Common Voice has no fakes, so it gets the share of its real clips rejected
    at the pooled threshold instead."""
    rows = []
    for (model, kind), g in scores.groupby(["model", "audio"]):
        pooled, threshold = eer(g.loc[g.label == "bonafide", "score"].values, g.loc[g.label == "spoof", "score"].values)
        rows.append({"model": model, "audio": kind, "source": "all (pooled)", "eer_pct": 100 * pooled})
        for source, s in g.groupby("source"):
            real, fake = s.loc[s.label == "bonafide", "score"].values, s.loc[s.label == "spoof", "score"].values
            if len(fake):
                rows.append({"model": model, "audio": kind, "source": source, "eer_pct": 100 * eer(real, fake)[0]})
            else:
                rows.append({"model": model, "audio": kind, "source": f"{source} (real rejected)",
                             "eer_pct": 100 * float((real <= threshold).mean())})
    table = pd.DataFrame(rows)
    table["eer_pct"] = table["eer_pct"].round(1)
    return table.pivot_table(index="source", columns=["model", "audio"], values="eer_pct", sort=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="append", required=True, metavar="NAME=WEIGHTS")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--split", default="test")
    parser.add_argument("--per-group", type=int, default=1000, help="clips per dataset and label")
    parser.add_argument("--threads", type=int, default=None, help="default: PyTorch's choice")
    parser.add_argument("--audio", choices=["both", "raw", "processed"], default="both")
    parser.add_argument("--out-folder", default=OUT_FOLDER, help="under --data-dir")
    parser.add_argument("--title", default="Pretrained baseline")
    args = parser.parse_args()
    if args.threads:
        torch.set_num_threads(args.threads)

    df = pd.read_parquet(args.data_dir / "manifest.processed.parquet")
    df = df[df["split"] == args.split]
    clips = df.sample(frac=1, random_state=0).groupby(["source", "label"]).head(args.per_group)
    print(f"{len(clips)} {args.split} clips, up to {args.per_group} per dataset and label")

    out_dir = args.data_dir / args.out_folder
    out_dir.mkdir(exist_ok=True)
    results = []
    for spec in args.model:
        name, weights = spec.split("=", 1)
        model = load_model(Path(weights))
        for raw in {"both": [True, False], "raw": [True], "processed": [False]}[args.audio]:
            kind = "raw" if raw else "processed"
            print(f"{name}, {kind} audio", flush=True)
            start = time.time()
            s = score(model, clips, args.data_dir, raw)
            print(f"  {len(clips) / (time.time() - start):.0f} clips a second", flush=True)
            results.append(clips[["utt_id", "source", "label", "attack_type"]].assign(model=name, audio=kind, score=s))

    scores = pd.concat(results, ignore_index=True)
    scores.to_csv(out_dir / "scores.csv", index=False)
    table = summarise(scores)
    flat = table.copy()
    flat.columns = [f"{m} ({a})" for m, a in flat.columns]
    counts = clips.groupby(["source", "label"]).size().unstack(fill_value=0).reset_index()
    report = [
        f"# {args.title}",
        f"EER (%) on {len(clips)} {args.split} clips, up to {args.per_group} per dataset and label. "
        "0 is perfect, 50 is guessing.",
        markdown_table(flat.reset_index()),
        "## Clips scored", markdown_table(counts),
        "## Models", json.dumps(dict(s.split("=", 1) for s in args.model), indent=2),
    ]
    (out_dir / "report.md").write_text("\n\n".join(report) + "\n", encoding="utf-8")
    print(flat.to_string())


if __name__ == "__main__":
    sys.exit(main())
