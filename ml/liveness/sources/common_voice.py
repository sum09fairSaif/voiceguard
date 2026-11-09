"""Mozilla Common Voice (English): real people reading sentences in a browser.

Every clip is bonafide. It's here because the clips were recorded the way
VoiceGuard records: through a web page, on whatever laptop or phone mic the
speaker had. ASVspoof's bonafide audio is clean studio speech, so without
this a model could learn "cheap mic means fake" and turn real users away.

The full English set is far bigger than we need, so we take a fixed slice
of each split (the same slice on every machine). Two releases are read:

- Current releases (train.tsv, clips/): a few clips from each speaker, which
  gives many voices without any one dominating. The train, dev and test
  lists have no speakers in common, so we keep them.
- The 2017 release on Kaggle (cv-valid-train.csv, cv-valid-train/): only
  the "valid" clips, which at least two listeners agreed match their text.
  It doesn't record who's speaking, so each clip gets its own speaker id:
  clips per speaker can't be capped, and the leak check can't tell whether
  a speaker is in more than one split.

Download a current English release from https://datacollective.mozillafoundation.org
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
# size. Clips are picked in a fixed order, so every teammate gets the same
# slice.
MAX_CLIPS = {"train": 20000, "dev": 2000, "test": 2000}


def _find_folder(root: Path) -> Path:
    if (root / "train.tsv").is_file() or (root / "cv-valid-train.csv").is_file():
        return root
    found = sorted(root.glob("cv-corpus-*/en/train.tsv"))
    if not found:
        raise FileNotFoundError(
            f"no train.tsv or cv-valid-train.csv in {root}, and no {root}/cv-corpus-*/en/"
        )
    return found[-1].parent  # the newest release, if there are several


def _row(utt: str, path: str, speaker: str, split: str) -> dict:
    return {
        "utt_id": f"{NAME}/{utt}",
        "path": path,
        "source": NAME,
        "speaker_id": f"{NAME}/{speaker}",
        "label": BONAFIDE,
        "attack_type": "",
        "split": split,
        "license": LICENSE,
    }


def _load_current(folder: Path, prefix: Path) -> list[dict]:
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
            path = (prefix / "clips" / record.path).as_posix()
            rows.append(_row(Path(record.path).stem, path, record.client_id, our_split))
    return rows


def _load_2017(folder: Path, prefix: Path) -> list[dict]:
    rows = []
    for their_split, our_split in SPLITS.items():
        # Columns: filename, text, up_votes, down_votes, age, gender, accent,
        # duration. filename is e.g. "cv-valid-train/sample-000000.mp3".
        clips = pd.read_csv(folder / f"cv-valid-{their_split}.csv", usecols=["filename"], dtype=str)
        # A fixed random sample: consecutive clips may come from one sitting.
        clips = clips.sample(n=min(MAX_CLIPS[our_split], len(clips)), random_state=0)
        for record in clips.itertuples(index=False):
            utt = Path(record.filename).with_suffix("").as_posix()  # "cv-valid-train/sample-000000"
            rows.append(_row(utt, (prefix / record.filename).as_posix(), f"unknown/{utt}", our_split))
    return rows


def load(root: Path) -> list[dict]:
    folder = _find_folder(root)
    prefix = folder.relative_to(root)
    if (folder / "cv-valid-train.csv").is_file():
        return _load_2017(folder, prefix)
    return _load_current(folder, prefix)
