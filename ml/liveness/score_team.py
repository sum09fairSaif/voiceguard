"""Score the team's recordings exactly as the live liveness check would.

Each clip in data/raw/team/metadata.csv (see sources/team.py) is decoded by
the model service's own ffmpeg command (model-service/app.py), prepared by
its liveness.prepare(), and scored window by window; the lowest window
counts, as in the app. This is what the backend's LIVENESS_THRESHOLD is
chosen on.

    python score_team.py --model xlsr=data/models/xlsr.pth --model first-try=data/models/first-try.pth

Needs requirements-model.txt (PyTorch, and transformers for XLS-R) and
ffmpeg on the PATH or FFMPEG_BINARY pointing at it. Writes
data/team-scores/scores.csv and prints how many live reads each threshold
rejects and how many replays it lets through, by split. The audio never
leaves this machine.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
# The model service's code, so the clips go through exactly what users' do.
sys.path.insert(0, str(HERE.parents[1] / "model-service"))

import liveness  # model-service/liveness.py
from app import FORMATS, decode_audio  # model-service/app.py

DEFAULT_DATA_DIR = HERE / "data"
THRESHOLDS = [0.5, 1.0, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0]


def score_clip(model, windows: np.ndarray | None) -> list[float]:
    """Every window's score; empty if there's nothing to score."""
    if windows is None:
        return []
    with torch.inference_mode():
        return [
            float(score)
            for i in range(0, len(windows), liveness.BATCH)
            for score in model(torch.from_numpy(windows[i : i + liveness.BATCH]))[1][:, 1]
        ]


def load(weights: Path):
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model = liveness.build_model(state)
    model.load_state_dict(state)
    return model.eval()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="append", required=True, metavar="NAME=WEIGHTS")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    team = args.data_dir / "raw" / "team"
    clips = list(csv.DictReader((team / "metadata.csv").open(encoding="utf-8")))
    prepared = {}
    for clip in clips:
        path = team / clip["file"]
        samples = decode_audio(path.read_bytes(), FORMATS[path.suffix.lower()])
        prepared[clip["file"]] = (len(samples), liveness.prepare(samples))

    rows = []
    for spec in args.model:
        name, weights = spec.split("=", 1)
        model = load(Path(weights))
        for clip in clips:
            length, windows = prepared[clip["file"]]
            scores = score_clip(model, windows)
            rows.append({
                "model": name, "file": clip["file"], "speaker": clip["speaker_id"], "label": clip["label"],
                "split": clip["split"], "seconds": round(length / liveness.TARGET_RATE, 2),
                "windows": len(scores), "score": min(scores) if scores else "",
                "window_scores": " ".join(f"{s:.2f}" for s in scores),
            })
        report(name, [r for r in rows if r["model"] == name])

    out = args.data_dir / "team-scores"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "scores.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {out / 'scores.csv'}")


def report(name: str, rows: list[dict]) -> None:
    # A clip with nothing to score fails the check, as in the app.
    print(f"\n{name}: live reads rejected / replays passing")
    for split in ["dev", "test"]:
        live = [r["score"] for r in rows if r["split"] == split and r["label"] == "bonafide"]
        fake = [r["score"] for r in rows if r["split"] == split and r["label"] == "spoof"]
        cells = []
        for threshold in THRESHOLDS:
            rejected = sum(s == "" or s < threshold for s in live)
            passed = sum(s != "" and s >= threshold for s in fake)
            cells.append(f"{threshold}: {rejected}/{len(live)}, {passed}/{len(fake)}")
        print(f"  {split:<5}", " | ".join(cells))


if __name__ == "__main__":
    main()
