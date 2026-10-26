"""CodecFake (Interspeech 2024): speech re-synthesized by 15 neural audio codecs.

Modern zero-shot voice cloning ("clone a voice from 3 seconds") generates
speech as neural-codec tokens, and older datasets have no fakes made that
way. Each codec here re-synthesizes the same VCTK recordings, so the only
difference between real and fake is the codec. The attack type is the
codec's name.

The dataset has no splits of its own, so speakers are split by a fixed
rule (about 80% train, 10% dev, 10% test), the same on every machine.

Caution: VCTK is also the source of ASVspoof 2019 LA's speech, so the same
people (under different speaker ids) are in both. Don't train on one and
report test scores on the other as if they were unseen speakers.

`python download.py codecfake` takes one shard per codec (about 4,400
clips each) and writes metadata.csv beside the audio.
"""

import hashlib
from pathlib import Path

import pandas as pd

from manifest import BONAFIDE, SPOOF

NAME = "codecfake"
LICENSE = "CC-BY-4.0"
LABELS = {"genuine": BONAFIDE, "spoofing": SPOOF}


def speaker_split(speaker: str) -> str:
    bucket = int(hashlib.sha256(speaker.encode()).hexdigest(), 16) % 10
    return "test" if bucket == 0 else "dev" if bucket == 1 else "train"


def load(root: Path) -> list[dict]:
    meta = root / "metadata.csv"
    if not meta.is_file():
        raise FileNotFoundError(f"{meta} not found; run `python download.py codecfake`")

    rows = []
    for record in pd.read_csv(meta, dtype=str).itertuples(index=False):
        if record.label not in LABELS:
            raise ValueError(f"{meta}: {record.file} has unknown label {record.label!r}")
        label = LABELS[record.label]
        rows.append({
            "utt_id": f"{NAME}/{Path(record.file).with_suffix('').as_posix()}",
            "path": record.file,
            "source": NAME,
            "speaker_id": f"{NAME}/{record.speaker_id}",
            "label": label,
            "attack_type": record.codec if label == SPOOF else "",
            "split": speaker_split(record.speaker_id),
            "license": LICENSE,
        })
    return rows
