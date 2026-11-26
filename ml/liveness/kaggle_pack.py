"""Get training ready to run on Kaggle's free GPUs.

From ml/liveness/, after preprocess.py:

    python kaggle_pack.py --user <kaggle-username>                  # the data and the script
    python kaggle_pack.py --user <kaggle-username> --script-only    # after changing the code
    python kaggle_pack.py --user <kaggle-username> --script-only --resume   # next session
    python kaggle_pack.py --user <kaggle-username> --noise-only     # echoes and noises, once
    python kaggle_pack.py --user <kaggle-username> --script-only --noise --name <run>   # train with them
    python kaggle_pack.py --user <kaggle-username> --extra-only asvspoof2017            # a dataset added later
    python kaggle_pack.py --user <kaggle-username> --script-only --extra --name <run>   # train with it too

Writes, in data/kaggle/:
- data/: the training clips and a dev sample, packed into a few big files
  (Kaggle uploads a few big files far faster than 300,000 small ones), plus
  the index, the starting weights and the noise files if you have them.
  About 15 GB. Upload it once, as a private dataset:
      kaggle datasets create -p data/kaggle/data
- script/: what Kaggle runs, with our training code bundled inside, so a code
  change only needs this pushed again, not the data:
      kaggle kernels push -p data/kaggle/script
- noise/ (with --noise-only): the room echoes and noises for augmentation,
  about 1.3 GB, as their own private dataset, so a data pack made without
  them doesn't have to be uploaded again:
      kaggle datasets create -p data/kaggle/noise
  Then pack the script with --noise to attach it.
- extra/ (with --extra-only <source>...): datasets added after data/ was
  uploaded, packed the same way as their own private dataset, so the 15 GB
  doesn't go up again:
      kaggle datasets create -p data/kaggle/extra
  (or `kaggle datasets version -p data/kaggle/extra -m "..."` to replace it).
  Then pack the script with --extra: on Kaggle its clips join data/'s.

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
NOISE_DATASET = "voiceguard-liveness-noise"
EXTRA_DATASET = "voiceguard-liveness-extra"
INDEX = "manifest.processed.parquet"
EXTRA_INDEX = "manifest.extra.parquet"
SCRIPT = "voiceguard-liveness-train"
WEIGHTS = "asvspoof5_aasist.pth"  # the starting point: the ASVspoof 5 baseline
WEIGHTS_SOURCE = "external/asvspoof5/Baseline-AASIST/models/weights/AASIST/best.pth"
NOISE_SOURCE = "augment/RIRS_NOISES"
NOISE_PACK = "rirs_noises.tar.gz"
# The uncompressed pack earlier versions made. Removed when packing, so an old
# one can't be uploaded or picked up beside the new one.
OLD_NOISE_PACK = "rirs_noises.tar"
CODE = ["audio.py", "augment.py", "manifest.py", "score_baseline.py", "train.py", "training_data.py",
        "validate.py", "models/__init__.py", "models/aasist.py", "models/ssl_aasist.py", "models/LICENSE-AASIST"]
# --arch ssl: wav2vec 2.0 XLS-R + AASIST. The front end is downloaded from
# Hugging Face on Kaggle (internet is on), so nothing extra is uploaded.
TRANSFORMERS = "transformers==5.21.1"
SSL_TRAIN_ARGS = ["--arch", "ssl", "--batch", "8", "--lr", "1e-4", "--ssl-lr", "1e-5"]
# What Kaggle has to install. It already has torch, numpy and pandas, and
# reinstalling our numpy over its own could break its torch, so only these.
# Their versions come from requirements.txt, so Kaggle trains on the same
# versions as everywhere else and Dependabot's bumps reach it too.
KAGGLE_INSTALLS = ["soxr", "soundfile", "miniaudio"]


def kaggle_pins(requirements: Path) -> list[str]:
    """KAGGLE_INSTALLS as pinned in requirements, e.g. ["soxr==1.1.0", ...]."""
    pins = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            pins[line.split("==", 1)[0].strip().lower()] = line
    missing = [name for name in KAGGLE_INSTALLS if name not in pins]
    if missing:
        raise ValueError(f"{requirements} doesn't pin {', '.join(missing)} with ==")
    return [pins[name] for name in KAGGLE_INSTALLS]


def choose_clips(data_dir: Path, sources: list[str] | None = None) -> pd.DataFrame:
    """All training clips, with groups over MAX_PER_GROUP thinned, and a dev
    sample; only from `sources` if given."""
    train = load_split(data_dir, "train")
    dev = load_split(data_dir, "dev")
    if sources:
        missing = sorted(set(sources) - set(train["source"]))
        if missing:
            raise SystemExit(f"no training clips from {', '.join(missing)}; run build_manifest.py, "
                             "validate.py and preprocess.py for it first")
        train, dev = train[train["source"].isin(sources)], dev[dev["source"].isin(sources)]
    parts = []
    for _, group in train.groupby(["source", "label"]):
        if len(group) > MAX_PER_GROUP:
            # The same share of every attack type, so none is lost.
            group = group.groupby("attack_type", group_keys=False).sample(
                frac=MAX_PER_GROUP / len(group), random_state=0)
        parts.append(group)
    dev = even_sample(dev, DEV_PER_GROUP)
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


def write_data(data_dir: Path, out: Path, workers: int | None, sources: list[str] | None = None) -> None:
    """The clips packed into shards in out, with their index. With
    `sources`, only those datasets' clips, indexed as EXTRA_INDEX, and
    without the starting weights or the noise (an --extra-only pack)."""
    clips = choose_clips(data_dir, sources)
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
                # One shard file at a time, swapped partway through the loop,
                # so a with-block would close it too early.
                handle = open(out / f"shard_{shard:03d}.bin", "wb")  # noqa: SIM115
            handle.write(data)
            where.append((f"shard_{shard:03d}.bin", offset, len(data), seconds))
            offset += len(data)
            if n % 50_000 == 0:
                print(f"  {n}/{len(clips)}", flush=True)
    handle.close()

    packed = pd.DataFrame(where, columns=["shard", "offset", "nbytes", "duration_s"])
    keep = ["utt_id", "source", "speaker_id", "label", "attack_type", "split"]
    index = pd.concat([clips[keep], packed], axis=1)
    index.to_parquet(out / (EXTRA_INDEX if sources else INDEX), index=False)
    if sources:
        print(f"{out}: {sum(f.stat().st_size for f in out.iterdir()) / 1e9:.2f} GB, "
              f"{index.groupby(['source', 'split', 'label']).size().to_dict()}")
        return
    shutil.copyfile(data_dir / WEIGHTS_SOURCE, out / WEIGHTS)

    if not write_noise(data_dir, out):
        print(f"no complete {data_dir / NOISE_SOURCE}: training on Kaggle will skip echo and noise "
              "unless the noise dataset is attached (see --noise-only)")
    gb = sum(f.stat().st_size for f in out.iterdir()) / 1e9
    print(f"{out}: {gb:.1f} GB, {index.groupby('split').size().to_dict()}")


def noise_usable(root: Path) -> bool:
    """Whether root holds both room echoes and noises, as augment.Augmenter
    needs (a half-copied or emptied folder doesn't)."""
    real = list(root.glob("real_rirs_isotropic_noises/*.wav"))
    echoes = any((root / "simulated_rirs").rglob("*.wav")) or any("noise" not in p.name for p in real)
    noises = any((root / "pointsource_noises").rglob("*.wav")) or any("noise" in p.name for p in real)
    return echoes and noises


def write_noise(data_dir: Path, out: Path) -> bool:
    """RIRS_NOISES as one gzipped tar file in out (3.6 GB of WAVs, about
    1.3 GB packed). False, with no pack left in out, if it hasn't been
    downloaded or isn't complete."""
    noise = data_dir / NOISE_SOURCE
    target = out / NOISE_PACK
    partial = out / f".{NOISE_PACK}.partial"
    # Whatever happens next, no older pack stays behind to be uploaded or used.
    for old in (target, out / OLD_NOISE_PACK, partial):
        old.unlink(missing_ok=True)
    if not noise.is_dir() or not noise_usable(noise):
        return False
    out.mkdir(parents=True, exist_ok=True)
    # Written beside the final name and moved in only when complete, so an
    # interrupted pack never leaves a corrupt archive under the real name.
    try:
        with tarfile.open(partial, "w:gz", compresslevel=6) as tar:
            tar.add(noise, arcname="RIRS_NOISES")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return True


def write_noise_metadata(out: Path, user: str) -> None:
    (out / "dataset-metadata.json").write_text(json.dumps({
        "title": NOISE_DATASET, "id": f"{user}/{NOISE_DATASET}", "licenses": [{"name": "apache-2.0"}],
        "description": "Room echoes and background noises for augmenting VoiceGuard liveness training "
                       "(private). OpenSLR 28, RIRS_NOISES, Apache 2.0.",
    }, indent=2))


def write_extra_metadata(out: Path, user: str, sources: list[str]) -> None:
    (out / "dataset-metadata.json").write_text(json.dumps({
        "title": EXTRA_DATASET, "id": f"{user}/{EXTRA_DATASET}", "licenses": [{"name": "other"}],
        "description": f"More VoiceGuard liveness training clips (private): {', '.join(sources)}, "
                       "under their own licences.",
    }, indent=2))


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


def noise_usable(root):
    # Both room echoes and noises, as augment.Augmenter needs. Checked here,
    # before train.py makes the run's folder, so a bad dataset can be fixed
    # and the run started again under the same name.
    root = Path(root)
    real = list(root.glob("real_rirs_isotropic_noises/*.wav"))
    echoes = any((root / "simulated_rirs").rglob("*.wav")) or any("noise" not in p.name for p in real)
    noises = any((root / "pointsource_noises").rglob("*.wav")) or any("noise" in p.name for p in real)
    return echoes and noises

NAME, EPOCHS, MAX_HOURS, RESUME, NOISE, EXTRA = {name!r}, {epochs}, {max_hours}, {resume}, {noise}, {extra}
TRAIN_ARGS, EXTRA_PACKAGES = {train_args!r}, {extra_packages!r}
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
subprocess.run([sys.executable, "-m", "pip", "install", "-q", *{pins!r}, *EXTRA_PACKAGES], check=True)

data = Path(find({index!r})[0]).parent
train_data = data
if EXTRA:
    # The extra dataset's clips join the main pack's: one index, with every
    # shard's full path (train.py joins them onto --data-dir, and joining a
    # full path keeps it as it is).
    import pandas as pd
    extra = find({extra_index!r})
    if not extra:
        sys.exit("--extra, but no {extra_index} in /kaggle/input; is the extra dataset attached?")
    main = pd.read_parquet(data / {index!r})
    main["shard"] = [str(data / s) for s in main["shard"]]
    more = pd.read_parquet(extra[0])
    more["shard"] = [str(Path(extra[0]).parent / s) for s in more["shard"]]
    more = more[~more["utt_id"].isin(main["utt_id"])]
    train_data = Path("/tmp/data")
    train_data.mkdir(parents=True, exist_ok=True)
    pd.concat([main, more], ignore_index=True).to_parquet(train_data / {index!r}, index=False)
    print("added", len(more), "clips from", extra[0], flush=True)
args = ["--name", NAME, "--data-dir", str(train_data), "--out-dir", str(work / "runs"), "--epochs", str(EPOCHS),
        "--max-hours", str(MAX_HOURS), "--workers", "4", *TRAIN_ARGS]

# The echoes and noises: unpacked if Kaggle unpacked them, or a tar file in
# the data pack or the separate noise dataset. The gzipped pack is the
# current one; a plain .tar is only used if there's no .tar.gz.
noise = [Path(hit).parent for hit in find("RIRS_NOISES/pointsource_noises")]
tars = find("rirs_noises.tar.gz") or find("rirs_noises.tar")
if not noise and tars:
    with tarfile.open(tars[0]) as t:  # into /tmp: /kaggle/working is kept as output
        t.extractall("/tmp/noise", filter="data")
    noise = [Path("/tmp/noise/RIRS_NOISES")]
noise = [root for root in noise if noise_usable(root)]
if NOISE and not noise:
    # Asked for echo and noise: don't spend GPU hours on a run without them.
    sys.exit("no usable room echoes and noises (RIRS_NOISES or rirs_noises.tar.gz) in /kaggle/input; "
             "is the noise dataset attached and complete?")
args += ["--noise-dir", str(noise[0])] if noise else ["--no-noise"]

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
elif "--arch" not in TRAIN_ARGS:
    args += ["--init", str(data / {weights!r})]

print("train.py", *args, flush=True)
subprocess.run([sys.executable, "train.py", *args], cwd=code, check=True)
'''


def write_script(here: Path, out: Path, user: str, name: str, epochs: int, max_hours: float, resume: bool,
                 noise: bool = False, arch: str = "aasist", extra: bool = False, rawboost: bool = False) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for file in CODE:
            tar.add(here / file, arcname=file)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.py").write_text(RUN_SCRIPT.format(
        name=name, epochs=epochs, max_hours=max_hours, resume=resume, noise=noise, extra=extra, weights=WEIGHTS,
        index=INDEX, extra_index=EXTRA_INDEX,
        pins=kaggle_pins(here / "requirements.txt"),
        train_args=(SSL_TRAIN_ARGS if arch == "ssl" else []) + (["--rawboost"] if rawboost else []),
        extra_packages=[TRANSFORMERS] if arch == "ssl" else [],
        code=base64.b64encode(buffer.getvalue()).decode()), encoding="utf-8")
    (out / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/{SCRIPT}", "title": SCRIPT, "code_file": "run.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [f"{user}/{DATASET}"] + ([f"{user}/{NOISE_DATASET}"] if noise else [])
        + ([f"{user}/{EXTRA_DATASET}"] if extra else []),
        # Its own last output, so the next session can carry on from last.pth.
        "kernel_sources": [f"{user}/{SCRIPT}"] if resume else [],
        "competition_sources": [],
    }, indent=2))
    print(f"{out / 'run.py'}: run {name!r} ({arch}), {epochs} epochs, up to {max_hours} h a session"
          + (", with echo and noise" if noise else "")
          + (", with RawBoost" if rawboost else "")
          + (", with the extra dataset" if extra else "")
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
    parser.add_argument("--noise-only", action="store_true", help="pack the echoes and noises as their own dataset")
    parser.add_argument("--noise", action="store_true",
                        help="attach the noise dataset, and stop on Kaggle if it isn't there")
    parser.add_argument("--extra-only", nargs="+", metavar="SOURCE",
                        help="pack these datasets as their own dataset, beside an already uploaded data/")
    parser.add_argument("--extra", action="store_true",
                        help="attach the extra dataset, and stop on Kaggle if it isn't there")
    parser.add_argument("--rawboost", action="store_true", help="train with RawBoost (augment.py)")
    parser.add_argument("--arch", choices=["aasist", "ssl"], default="aasist",
                        help="ssl: wav2vec 2.0 XLS-R + AASIST (models/ssl_aasist.py)")
    args = parser.parse_args()

    out = args.data_dir / "kaggle"
    if args.noise_only:
        if not write_noise(args.data_dir, out / "noise"):
            raise SystemExit(f"no complete {args.data_dir / NOISE_SOURCE}; run `python download.py rirs_noises` first")
        write_noise_metadata(out / "noise", args.user)
        print(f"{out / 'noise'}: upload once with `kaggle datasets create -p {out / 'noise'}`")
        return
    if args.extra_only:
        write_data(args.data_dir, out / "extra", args.workers, sources=args.extra_only)
        write_extra_metadata(out / "extra", args.user, args.extra_only)
        print(f"{out / 'extra'}: upload with `kaggle datasets create -p {out / 'extra'}`")
        return
    if not args.script_only:
        write_data(args.data_dir, out / "data", args.workers)
    if (out / "data").is_dir():
        write_dataset_metadata(out / "data", args.user)
    write_script(Path(__file__).parent, out / "script", args.user, args.name, args.epochs, args.max_hours,
                 args.resume, args.noise, args.arch, args.extra, args.rawboost)


if __name__ == "__main__":
    main()
