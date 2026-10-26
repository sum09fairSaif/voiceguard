"""The manifest: one table listing every clip from every dataset.

Each dataset labels its audio in its own way (protocol files, CSVs, folder
names). A loader in sources/ reads one dataset's labels and returns rows in
the shape below, so everything after loading (validation, preprocessing,
splitting, training) reads only the manifest and never a dataset's own
format.

Paths are relative to the data folder, so the same manifest works on every
teammate's machine wherever they keep the audio.
"""

from pathlib import Path

import pandas as pd

BONAFIDE = "bonafide"  # a live human speaking
SPOOF = "spoof"  # anything else: AI-generated, converted or replayed
LABELS = {BONAFIDE, SPOOF}
SPLITS = {"train", "dev", "test"}

# Filled in by the loaders, from each dataset's own labels.
LABEL_COLUMNS = [
    "utt_id",  # unique across all datasets: "<source>/<the dataset's own id>"
    "path",  # relative to the data folder
    "source",  # which loader produced the row
    "speaker_id",  # also prefixed with the source, so ids never collide
    "label",  # BONAFIDE or SPOOF
    "attack_type",  # how a spoof was made (e.g. ASVspoof's "A07"); "" if bonafide
    "split",  # train, dev or test
    "license",  # the dataset's license, so we know what we may do with it
]

# Filled in by build_manifest.py, from the audio files themselves.
AUDIO_COLUMNS = [
    "duration_s",
    "sample_rate",
    "channels",
    "format",  # container, e.g. FLAC, WAV, MP3
    "sha256",  # of the file, for finding duplicates
]

COLUMNS = LABEL_COLUMNS + AUDIO_COLUMNS


def check_rows(rows: list[dict], source: str) -> None:
    """Fail early, naming the loader, if a loader returned a bad row."""
    for row in rows:
        missing = [c for c in LABEL_COLUMNS if c not in row]
        if missing:
            raise ValueError(f"{source}: row {row.get('utt_id')} is missing {missing}")
        if row["label"] not in LABELS:
            raise ValueError(f"{source}: row {row['utt_id']} has label {row['label']!r}")
        if row["split"] not in SPLITS:
            raise ValueError(f"{source}: row {row['utt_id']} has split {row['split']!r}")
        if row["label"] == BONAFIDE and row["attack_type"]:
            raise ValueError(f"{source}: bonafide row {row['utt_id']} has an attack type")


def save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_parquet(path, index=False)


def load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns {missing}; rebuild it")
    return df
