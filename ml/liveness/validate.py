"""Check every clip in the manifest and write a report before anything trains.

From ml/liveness/, after build_manifest.py:

    python validate.py

Decodes each clip and flags ones that are missing, unreadable, too short,
silent or badly clipped. Also finds duplicate files and speakers that
appear in more than one split (which would let a model pass the test by
recognizing voices it trained on).

Writes, in data/:
- manifest.clean.parquet: the manifest without the flagged clips and with
  one copy of each duplicate. Later steps read this one.
- issues.csv: every flagged clip and why.
- report.md: clip counts by source, split and label, plus the problems found.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

import manifest

DEFAULT_DATA_DIR = Path(__file__).parent / "data"
MIN_SECONDS = 1.0  # shorter than this isn't enough to judge liveness
# The same measures the model service uses for enrollment samples.
SPEECH_LEVEL = 0.01  # a clip whose loudest sample is quieter than this is silent
CLIPPED_LEVEL = 0.99  # a sample this close to full scale was cut off
MAX_CLIPPED_SHARE = 0.01  # more than 1% cut-off samples is badly clipped


def check_clip(path: Path) -> str:
    """The problem with one clip, or "" if it's fine."""
    if not path.is_file():
        return "missing"
    try:
        samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError):
        return "unreadable"
    if not np.isfinite(samples).all():
        return "not_finite"
    if len(samples) / rate < MIN_SECONDS:
        return "too_short"
    peak = np.abs(samples).max()
    if peak < SPEECH_LEVEL:
        return "silent"
    if (np.abs(samples) >= CLIPPED_LEVEL).mean() > MAX_CLIPPED_SHARE:
        return "clipped"
    return ""


def find_duplicates(df: pd.DataFrame) -> pd.Series:
    """Why each row should be dropped as a duplicate, or "".

    The first copy of a file is kept. If copies disagree on the label or
    split, all of them are dropped: we can't tell which is right, and the
    same audio in train and test would inflate the test score.
    """
    reason = pd.Series("", index=df.index)
    hashed = df[df["sha256"] != ""]
    for _, copies in hashed.groupby("sha256"):
        if len(copies) < 2:
            continue
        if copies["label"].nunique() > 1 or copies["split"].nunique() > 1:
            reason[copies.index] = "duplicate_conflict"
        else:
            reason[copies.index[1:]] = "duplicate"
    return reason


def leaking_speakers(df: pd.DataFrame) -> pd.Series:
    """Speakers with clips in more than one split, and which splits."""
    splits = df.groupby("speaker_id")["split"].unique()
    return splits[splits.map(len) > 1].map(lambda s: ", ".join(sorted(s)))


def markdown_table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    divider = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(map(str, row)) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, divider, *body])


def write_report(df: pd.DataFrame, issues: pd.DataFrame, leaks: pd.Series, path: Path) -> None:
    clean = df.drop(issues.index)
    counts = (
        clean.groupby(["source", "split", "label"]).size().unstack("label", fill_value=0).reset_index()
    )
    hours = clean.groupby("source")["duration_s"].sum().div(3600).round(1).reset_index(name="hours")
    rates = clean.groupby(["source", "sample_rate"]).size().reset_index(name="clips")
    attacks = (
        clean[clean["label"] == manifest.SPOOF]
        .groupby(["source", "split", "attack_type"]).size().reset_index(name="clips")
    )
    problems = issues["issue"].value_counts().rename_axis("issue").reset_index(name="clips")

    sections = [
        "# Liveness dataset report",
        f"{len(df)} clips in the manifest; {len(clean)} kept, {len(issues)} flagged.",
        "## Clips kept, by source, split and label", markdown_table(counts),
        "## Hours of audio kept", markdown_table(hours),
        "## Sample rates (resampled to 16 kHz in preprocessing)", markdown_table(rates),
        "## Spoof clips by attack type", markdown_table(attacks) if len(attacks) else "None.",
        "## Flagged clips (details in issues.csv)", markdown_table(problems) if len(problems) else "None.",
        "## Speakers in more than one split",
        (
            f"**{len(leaks)} speakers appear in more than one split.** Fix the split before "
            "trusting any test score.\n\n" + markdown_table(leaks.reset_index(name="splits").head(20))
            if len(leaks) else "None."
        ),
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def validate(
    df: pd.DataFrame, data_dir: Path, workers: int | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Returns the clean manifest, the flagged clips, and the leaking speakers."""
    paths = [data_dir / p for p in df["path"]]
    with ProcessPoolExecutor(workers) as pool:
        problems = pd.Series(list(pool.map(check_clip, paths, chunksize=64)), index=df.index)

    duplicates = find_duplicates(df)
    problems = problems.where(problems != "", duplicates)
    flagged = df[problems != ""].assign(issue=problems[problems != ""])
    issues = flagged[["utt_id", "path", "source", "label", "split", "issue"]]
    leaks = leaking_speakers(df.drop(issues.index))
    return df.drop(issues.index), issues, leaks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--workers", type=int, default=None, help="default: one per CPU")
    args = parser.parse_args()

    df = manifest.load(args.data_dir / "manifest.parquet")
    clean, issues, leaks = validate(df, args.data_dir, args.workers)
    manifest.save(clean, args.data_dir / "manifest.clean.parquet")
    issues.to_csv(args.data_dir / "issues.csv", index=False)
    write_report(df, issues, leaks, args.data_dir / "report.md")
    print(f"Kept {len(clean)} of {len(df)} clips; {len(issues)} flagged.")
    if len(leaks):
        print(f"Warning: {len(leaks)} speakers appear in more than one split; see report.md.")
    print(f"Report: {args.data_dir / 'report.md'}")


if __name__ == "__main__":
    main()
