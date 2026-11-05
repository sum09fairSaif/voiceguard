"""Turn every clean clip into the same kind of audio, ready to train on.

From ml/liveness/, after validate.py:

    python preprocess.py               # everything; about 45 minutes, and safe to stop
    python preprocess.py --sample 200  # a quick trial: 200 clips per source and label

Each clip becomes 16 kHz mono FLAC, with the silence at both ends trimmed and
the speech brought to the same loudness (the steps are in audio.py). The raw
audio is never changed. Clips stay full length: they're cut to AASIST's 4
seconds when loaded, so training can use all of a long clip.

Stop it whenever you like. Finished clips are noted in data/processed/progress.csv,
and running the same command again carries on from there.

Writes, in data/:
- processed/<source>/...: the audio, in the same folders as under raw/.
- manifest.processed.parquet: the clean manifest pointing at the new files,
  plus raw_path and what was done to each clip. Training reads this one.
- preprocess_issues.csv: clips dropped because of what preprocessing found.
- preprocess_report.md: how much was trimmed, by source and label.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

import audio
import manifest
from validate import DEFAULT_DATA_DIR, MAX_VALID_PEAK, markdown_table

OUT_FOLDER = "processed"
# Lower than validate.py's 1 second: that limit counts silence, this one
# doesn't, and 1 second here would drop real clips far more often than fakes.
MIN_SPEECH_SECONDS = 0.5
FIELDS = ["utt_id", "path", "duration_s", "lead_trim_s", "tail_trim_s", "gain_db", "sha256", "issue"]
SETTINGS = {
    "MIN_SPEECH_SECONDS": MIN_SPEECH_SECONDS,
    **{
        name: getattr(audio, name)
        for name in ["TARGET_RATE", "FRAME_SECONDS", "HOP_SECONDS", "TRIM_DB", "ACTIVE_DB",
                     "TARGET_DBFS", "MAX_PEAK", "STEPS_VERSION"]
    },
}


def processed_path(raw_path: str) -> str:
    """raw/<source>/a/b.mp3 becomes processed/<source>/a/b.flac."""
    relative = Path(raw_path).relative_to("raw").with_suffix(".flac")
    return f"{OUT_FOLDER}/{relative.as_posix()}"


def process_clip(job: tuple[str, str, Path]) -> dict:
    """Clean one clip and write it. Returns one row of progress.csv."""
    utt_id, raw_path, data_dir = job
    out_path = processed_path(raw_path)
    row = dict.fromkeys(FIELDS, "") | {"utt_id": utt_id, "path": out_path}
    try:
        samples, rate = sf.read(str(data_dir / raw_path), dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError):
        return row | {"issue": "unreadable"}
    if not np.isfinite(samples).all() or np.abs(samples).max() > MAX_VALID_PEAK:
        return row | {"issue": "corrupt"}

    clip, steps = audio.clean(samples, rate)
    if len(clip) == 0:
        return row | {"issue": "silent"}
    duration = len(clip) / audio.TARGET_RATE
    if duration < MIN_SPEECH_SECONDS:
        return row | {"issue": "too_short_after_trim"}

    buffer = io.BytesIO()
    sf.write(buffer, clip, audio.TARGET_RATE, format="FLAC", subtype="PCM_16")
    encoded = buffer.getvalue()

    # Written to a temporary name first, so stopping midway can't leave half a file.
    target = data_dir / out_path
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".partial")
    partial.write_bytes(encoded)
    os.replace(partial, target)
    return row | steps | {"duration_s": duration, "sha256": hashlib.sha256(encoded).hexdigest()}


def check_settings(out_dir: Path) -> None:
    """Refuse to mix clips made with different settings in one folder."""
    path = out_dir / "settings.json"
    if path.exists() and json.loads(path.read_text()) != SETTINGS:
        sys.exit(f"audio.py settings changed since {out_dir} was made; delete that folder and run again")
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(SETTINGS, indent=2))


def drop_torn_line(path: Path) -> None:
    """Cut off a half-written last row, left if the last run was killed. That
    clip counts as not done, so it's simply processed again."""
    if not path.exists():
        return
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        tail = b""
        while size and b"\n" not in tail:
            step = min(1 << 16, size)
            size -= step
            f.seek(size)
            tail = f.read(step) + tail
        f.truncate(size + tail.rfind(b"\n") + 1)


def run_jobs(df: pd.DataFrame, data_dir: Path, workers: int | None) -> None:
    """Process every clip in df not already in progress.csv."""
    out_dir = data_dir / OUT_FOLDER
    check_settings(out_dir)
    progress = out_dir / "progress.csv"
    drop_torn_line(progress)
    done = set(pd.read_csv(progress, usecols=["utt_id"])["utt_id"]) if progress.exists() else set()
    todo = df[~df["utt_id"].isin(done)]
    jobs = [(utt_id, path, data_dir) for utt_id, path in zip(todo["utt_id"], todo["path"])]
    print(f"{len(done)} clips already done, {len(jobs)} to do")

    is_new = not progress.exists()
    with open(progress, "a", newline="") as f, ProcessPoolExecutor(workers) as pool:
        writer = csv.DictWriter(f, FIELDS)
        if is_new:
            writer.writeheader()
        for n, row in enumerate(pool.map(process_clip, jobs, chunksize=64), start=1):
            writer.writerow(row)
            if n % 10000 == 0:
                f.flush()
                print(f"{n}/{len(jobs)} clips", flush=True)


def collect(df: pd.DataFrame, data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join the finished work back onto the manifest. Returns (kept, dropped)."""
    results = pd.read_csv(data_dir / OUT_FOLDER / "progress.csv", keep_default_na=False)
    results = results.drop_duplicates("utt_id", keep="last")
    merged = df.rename(columns={"path": "raw_path"}).drop(columns=["duration_s", "sha256"])
    merged = merged.merge(results, on="utt_id")

    dropped = merged[merged["issue"] != ""]
    issues = dropped[["utt_id", "raw_path", "source", "label", "split", "issue"]]
    kept = merged[merged["issue"] == ""].drop(columns="issue").reset_index(drop=True)
    for column in ["duration_s", "lead_trim_s", "tail_trim_s", "gain_db"]:
        kept[column] = kept[column].astype(float)
    kept = kept.assign(sample_rate=audio.TARGET_RATE, channels=1, format="FLAC")
    extras = ["raw_path", "lead_trim_s", "tail_trim_s", "gain_db"]
    return kept[manifest.COLUMNS + extras], issues


def write_report(df: pd.DataFrame, kept: pd.DataFrame, issues: pd.DataFrame, path: Path) -> None:
    """Silence at the ends of clips is a known giveaway in these datasets, so
    the report compares what was trimmed from real and fake clips."""
    medians = (
        kept.groupby(["source", "label"])[["duration_s", "lead_trim_s", "tail_trim_s", "gain_db"]]
        .median().round(2).reset_index()
    )
    clips = kept.groupby(["source", "label"]).size().reset_index(name="clips")
    table = clips.merge(medians, on=["source", "label"])
    counts = (
        issues.groupby(["source", "issue", "label"]).size().reset_index(name="clips")
        if len(issues) else None
    )
    sections = [
        "# Preprocessing report",
        f"{len(df)} clean clips; {len(kept)} processed, {len(issues)} dropped.",
        f"{kept['duration_s'].sum() / 3600:.1f} hours of audio kept.",
        "## Medians by source and label", markdown_table(table),
        "## Dropped clips", markdown_table(counts) if counts is not None else "None.",
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def sample_clips(df: pd.DataFrame, per_group: int) -> pd.DataFrame:
    """The same clips every time, from every source and label."""
    return df.sample(frac=1, random_state=0).groupby(["source", "label"]).head(per_group)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--workers", type=int, default=None, help="default: one per CPU")
    parser.add_argument("--sample", type=int, help="only this many clips per source and label")
    args = parser.parse_args()

    df = manifest.load(args.data_dir / "manifest.clean.parquet")
    if args.sample:
        df = sample_clips(df, args.sample)
    run_jobs(df, args.data_dir, args.workers)
    kept, issues = collect(df, args.data_dir)
    kept.to_parquet(args.data_dir / "manifest.processed.parquet", index=False)
    issues.to_csv(args.data_dir / "preprocess_issues.csv", index=False)
    write_report(df, kept, issues, args.data_dir / "preprocess_report.md")
    print(f"Kept {len(kept)} of {len(df)} clips; {len(issues)} dropped.")
    print(f"Report: {args.data_dir / 'preprocess_report.md'}")


if __name__ == "__main__":
    main()
