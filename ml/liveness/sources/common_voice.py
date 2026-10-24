"""Mozilla Common Voice (English): real people reading sentences in a browser.

Every clip is bonafide. It's here because the clips were recorded the way
VoiceGuard records: through a web page, on whatever laptop or phone mic the
speaker had. ASVspoof's bonafide audio is clean studio speech, so without
this a model could learn "cheap mic means fake" and turn real users away.

The full English set is far bigger than we need, so we take a slice: a few
clips from each speaker, which gives many voices without any one speaker
dominating. Common Voice's own train, dev and test lists have no speakers in
common, so we keep them.

Download the English dataset from https://datacollective.mozillafoundation.org
(search "Common Voice") and unzip it into data/raw/common_voice/, so that
folder holds train.tsv, dev.tsv, test.tsv and clips/ (or a cv-corpus-*/en/
folder containing them).
"""

import csv
from pathlib import Path

import pandas as pd

from manifest import BONAFIDE

NAME = "common_voice"
LICENSE = "CC0-1.0"
SPLITS = {"train": "train", "dev": "dev", "test": "test"}
CLIPS_PER_SPEAKER = 5
# The most clips taken from each split, so the slice stays a manageable
# download-and-process size. Speakers are taken in a fixed order, so every
# teammate gets the same slice.
MAX_CLIPS = {"train": 20000, "dev": 2000, "test": 2000}


def _find_folder(root: Path) -> Path:
    if (root / "train.tsv").is_file():
        return root
    found = sorted(root.glob("cv-corpus-*/en/train.tsv"))
    if not found:
        raise FileNotFoundError(f"no train.tsv in {root} or {root}/cv-corpus-*/en/")
    return found[-1].parent  # the newest release, if there are several


def load(root: Path) -> list[dict]:
    folder = _find_folder(root)
    prefix = folder.relative_to(root)

    rows = []
    for their_split, our_split in SPLITS.items():
        # Sentences can contain quote marks, so quoting is switched off.
        clips = pd.read_csv(
            folder / f"{their_split}.tsv",
            sep="\t",
            usecols=["client_id", "path"],
            quoting=csv.QUOTE_NONE,
            dtype=str,
        )
        clips = (
            clips.sort_values(["client_id", "path"])
            .groupby("client_id")
            .head(CLIPS_PER_SPEAKER)
            .head(MAX_CLIPS[our_split])
        )
        for record in clips.itertuples(index=False):
            rows.append({
                "utt_id": f"{NAME}/{Path(record.path).stem}",
                "path": (prefix / "clips" / record.path).as_posix(),
                "source": NAME,
                "speaker_id": f"{NAME}/{record.client_id}",
                "label": BONAFIDE,
                "attack_type": "",
                "split": our_split,
                "license": LICENSE,
            })
    return rows
