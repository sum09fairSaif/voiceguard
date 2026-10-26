"""In-the-Wild: real deepfakes of public figures, collected from the internet.

About 20 hours from 58 politicians and celebrities, bonafide and spoof
for each. The fakes come from unknown tools, so they're the closest thing
we have to what an attacker would actually use. Models that score well on
ASVspoof often do much worse here.

That makes it a generalization test only: every row goes in the test split
and it's never used for training or for choosing thresholds.

Download release_in_the_wild.zip from https://deepfake-total.com/in_the_wild
and unzip it into data/raw/in_the_wild/, so that folder holds meta.csv (or
a release_in_the_wild/ folder containing it).
"""

from pathlib import Path

import pandas as pd

from manifest import BONAFIDE, SPOOF

NAME = "in_the_wild"
LICENSE = "research use; see https://deepfake-total.com/in_the_wild"
LABELS = {"bona-fide": BONAFIDE, "spoof": SPOOF}


def load(root: Path) -> list[dict]:
    folder = root / "release_in_the_wild" if (root / "release_in_the_wild").is_dir() else root
    meta = folder / "meta.csv"
    if not meta.is_file():
        raise FileNotFoundError(f"{meta} not found; unzip release_in_the_wild.zip into {root}")
    prefix = folder.relative_to(root)

    # Columns: file, speaker, label ("bona-fide" or "spoof").
    rows = []
    for record in pd.read_csv(meta).itertuples(index=False):
        if record.label not in LABELS:
            raise ValueError(f"{meta}: {record.file} has unknown label {record.label!r}")
        label = LABELS[record.label]
        rows.append({
            "utt_id": f"{NAME}/{Path(record.file).stem}",
            "path": (prefix / record.file).as_posix(),
            "source": NAME,
            "speaker_id": f"{NAME}/{record.speaker}",
            "label": label,
            # The tools that made these fakes aren't known.
            "attack_type": "unknown" if label == SPOOF else "",
            "split": "test",
            "license": LICENSE,
        })
    return rows
