"""Get training ready to run on Kaggle's free GPUs.

From ml/liveness/, after preprocess.py:

    python kaggle_pack.py --user <kaggle-username>                  # the data and the script
    python kaggle_pack.py --user <kaggle-username> --script-only    # after changing the code
    python kaggle_pack.py --user <kaggle-username> --script-only --resume   # next session

Writes, in data/kaggle/:
- data/: the training clips and a dev sample, packed into a few big files
  (Kaggle uploads a few big files far faster than 300,000 small ones), plus
  the index, the starting weights and the noise files if you have them.
  About 15 GB. Upload it once, as a private dataset:
      kaggle datasets create -p data/kaggle/data
- script/: what Kaggle runs, with our training code bundled inside, so a code
  change only needs this pushed again, not the data:
      kaggle kernels push -p data/kaggle/script

To keep the upload small, without losing anything training would use:
- clips are cut to their first 5 seconds (training takes 4-second windows);
- no dataset keeps more than 80,000 clips of one label. Only ASVspoof 5's
  fakes are over that; they're thinned evenly across attack types.
"""

import argparse
import base64
import io
import json
import shutil
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import soundfile as sf

import audio
from training_data import even_sample, load_split
from validate import DEFAULT_DATA_DIR

MAX_SECONDS = 5.0
MAX_PER_GROUP = 80_000
DEV_PER_GROUP = 500
SHARD_BYTES = 2_000_000_000
DATASET = "voiceguard-liveness-data"
SCRIPT = "voiceguard-liveness-train"
WEIGHTS = "asvspoof5_aasist.pth"  # the starting point: the ASVspoof 5 baseline
WEIGHTS_SOURCE = "external/asvspoof5/Baseline-AASIST/models/weights/AASIST/best.pth"
NOISE_SOURCE = "augment/RIRS_NOISES"
CODE = ["audio.py", "augment.py", "manifest.py", "score_baseline.py", "train.py", "training_data.py",
        "validate.py", "models/__init__.py", "models/aasist.py", "models/LICENSE-AASIST"]


def choose_clips(data_dir: Path) -> pd.DataFrame:
    """All training clips, with groups over MAX_PER_GROUP thinned, and a dev sample."""
    train = load_split(data_dir, "train")
    parts = []
    for _, group in train.groupby(["source", "label"]):
        if len(group) > MAX_PER_GROUP:
            # The same share of every attack type, so none is lost.
            group = group.groupby("attack_type", group_keys=False).sample(
                frac=MAX_PER_GROUP / len(group), random_state=0)
        parts.append(group)
    dev = even_sample(load_split(data_dir, "dev"), DEV_PER_GROUP)
    return pd.concat(parts + [dev], ignore_index=True)


def clip_bytes(path: str) -> tuple[bytes, float]:
    """The clip's FLAC file, re-encoded if it has to be cut to MAX_SECONDS."""
    info = sf.info(path)
    limit = int(MAX_SECONDS * audio.TARGET_RATE)
    if info.frames <= limit:
        return Path(path).read_bytes(), info.frames / info.samplerate
    samples, rate = sf.read(path, frames=limit, dtype="float32")
    buffer = io.BytesIO()
    sf.write(buffer, samples, rate, format="FLAC", subtype="PCM_16")
    return buffer.getvalue(), limit / rate


def write_data(data_dir: Path, out: Path, workers: int | None) -> None:
    clips = choose_clips(data_dir)
    print(f"packing {len(clips)} clips")
    out.mkdir(parents=True, exist_ok=True)
    shard, offset, handle = -1, SHARD_BYTES, None
    where = []
    paths = [str(data_dir / p) for p in clips["path"]]
    with ProcessPoolExecutor(workers) as pool:
        for n, (data, seconds) in enumerate(pool.map(clip_bytes, paths, chunksize=64), start=1):
            if offset + len(data) > SHARD_BYTES:
                if handle:
                    handle.close()
                shard, offset = shard + 1, 0
                handle = open(out / f"shard_{shard:03d}.bin", "wb")
            handle.write(data)
            where.append((f"shard_{shard:03d}.bin", offset, len(data), seconds))
            offset += len(data)
            if n % 50_000 == 0:
                print(f"  {n}/{len(clips)}", flush=True)
    handle.close()

    packed = pd.DataFrame(where, columns=["shard", "offset", "nbytes", "duration_s"])
    keep = ["utt_id", "source", "speaker_id", "label", "attack_type", "split"]
    index = pd.concat([clips[keep], packed], axis=1)
    index.to_parquet(out / "manifest.processed.parquet", index=False)
    shutil.copyfile(data_dir / WEIGHTS_SOURCE, out / WEIGHTS)

    noise = data_dir / NOISE_SOURCE
    if noise.is_dir():
        with tarfile.open(out / "rirs_noises.tar", "w") as tar:
            tar.add(noise, arcname="RIRS_NOISES")
    else:
        print(f"no {noise}: training on Kaggle will skip echo and noise (compression still applies)")
    gb = sum(f.stat().st_size for f in out.iterdir()) / 1e9
    print(f"{out}: {gb:.1f} GB, {index.groupby('split').size().to_dict()}")


def write_dataset_metadata(out: Path, user: str) -> None:
    """Kaggle's description of the dataset. Rewritten every time, so the
    username can be changed without packing the data again."""
    (out / "dataset-metadata.json").write_text(json.dumps({
        "title": DATASET, "id": f"{user}/{DATASET}", "licenses": [{"name": "other"}],
        "description": "VoiceGuard liveness training clips (private). From ASVspoof 2019 LA/PA, "
                       "ASVspoof 5, CodecFake and Common Voice, under their own licences.",
    }, indent=2))


RUN_SCRIPT = '''"""VoiceGuard liveness training on Kaggle. Made by kaggle_pack.py; don't edit by hand.

Finds the data, unpacks the bundled code, and runs train.py. If an earlier
run's output is attached (kaggle_pack.py --resume), it carries on from there.
"""
import base64, glob, io, subprocess, sys, tarfile
from pathlib import Path

NAME, EPOCHS, MAX_HOURS, RESUME = {name!r}, {epochs}, {max_hours}, {resume}
CODE = {code!r}


def find(pattern):
    for depth in range(1, 6):  # Kaggle has mounted inputs at different depths over time
        hits = sorted(glob.glob("/kaggle/input/" + "*/" * depth + pattern))
        if hits:
            return hits
    return []


work = Path("/kaggle/working")
code = work / "code"
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(CODE))) as t:
    t.extractall(code, filter="data")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "soxr==0.5.0.post1", "soundfile==0.13.1"], check=True)

data = Path(find("manifest.processed.parquet")[0]).parent
args = ["--name", NAME, "--data-dir", str(data), "--out-dir", str(work / "runs"), "--epochs", str(EPOCHS),
        "--max-hours", str(MAX_HOURS), "--workers", "4"]

noise = find("RIRS_NOISES/pointsource_noises")
if not noise and (data / "rirs_noises.tar").exists():
    with tarfile.open(data / "rirs_noises.tar") as t:  # into /tmp: /kaggle/working is kept as output
        t.extractall("/tmp/noise", filter="data")
    noise = ["/tmp/noise/RIRS_NOISES/pointsource_noises"]
args += ["--noise-dir", str(Path(noise[0]).parent)] if noise else ["--no-noise"]

previous = find(f"runs/{{NAME}}/last.pth")
if previous:
    import shutil
    shutil.copytree(Path(previous[0]).parent, work / "runs" / NAME, dirs_exist_ok=True)
    args.append("--resume")
elif RESUME:
    # Kaggle attaches the last version that finished without an error, so a
    # crashed session leaves nothing to carry on from. Stop rather than start over.
    for depth in range(1, 5):
        print(*sorted(glob.glob("/kaggle/input/" + "*/" * depth)), sep="\\n")
    sys.exit(f"no runs/{{NAME}}/last.pth in the inputs above, so there's nothing to carry on from")
else:
    args += ["--init", str(data / {weights!r})]

print("train.py", *args, flush=True)
subprocess.run([sys.executable, "train.py", *args], cwd=code, check=True)
'''


def write_script(here: Path, out: Path, user: str, name: str, epochs: int, max_hours: float, resume: bool) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for file in CODE:
            tar.add(here / file, arcname=file)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.py").write_text(RUN_SCRIPT.format(
        name=name, epochs=epochs, max_hours=max_hours, resume=resume, weights=WEIGHTS,
        code=base64.b64encode(buffer.getvalue()).decode()), encoding="utf-8")
    (out / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/{SCRIPT}", "title": SCRIPT, "code_file": "run.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [f"{user}/{DATASET}"],
        # Its own last output, so the next session can carry on from last.pth.
        "kernel_sources": [f"{user}/{SCRIPT}"] if resume else [],
        "competition_sources": [],
    }, indent=2))
    print(f"{out / 'run.py'}: run {name!r}, {epochs} epochs, up to {max_hours} h a session"
          + (", carrying on from the last session" if resume else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", required=True, help="your Kaggle username")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--name", default="first-try", help="the training run's name")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--max-hours", type=float, default=8.0, help="Kaggle stops a session at 9-12 hours")
    parser.add_argument("--script-only", action="store_true", help="don't redo the data")
    parser.add_argument("--resume", action="store_true", help="carry on from the last session's output")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    out = args.data_dir / "kaggle"
    if not args.script_only:
        write_data(args.data_dir, out / "data", args.workers)
    if (out / "data").is_dir():
        write_dataset_metadata(out / "data", args.user)
    write_script(Path(__file__).parent, out / "script", args.user, args.name, args.epochs, args.max_hours,
                 args.resume)


if __name__ == "__main__":
    main()
