"""Our own recordings, captured through the VoiceGuard app.

This is the data closest to production: live reads of the prompted passages,
replays of those reads played through a phone or laptop speaker, and voice
clones of teammates who agreed to it. The liveness threshold is chosen on
this set, so it's never used for training.

Everyone recorded must have given written consent. Speaker ids are codes
like "spk01", never names.

Put the recordings in data/raw/team/ with a metadata.csv beside them:

    file,speaker_id,label,attack_type,split
    spk01/live_01.webm,spk01,bonafide,,dev
    spk01/replay_01.webm,spk01,spoof,replay,dev
    spk02/clone_01.webm,spk02,spoof,voice_clone,test

- label: bonafide or spoof
- attack_type: blank for bonafide; for a spoof, one of ATTACK_TYPES
- split: dev (for choosing the threshold) or test (for the final score).
  Keep each speaker in one split only.
"""

from pathlib import Path

import pandas as pd

from manifest import BONAFIDE, LABELS

NAME = "team"
LICENSE = "private; VoiceGuard team only, with written consent"
ATTACK_TYPES = {"replay", "tts", "voice_clone"}
SPLITS = {"dev", "test"}
REQUIRED = ["file", "speaker_id", "label", "attack_type", "split"]


def load(root: Path) -> list[dict]:
    meta = root / "metadata.csv"
    if not meta.is_file():
        raise FileNotFoundError(f"{meta} not found; see sources/team.py for its format")
    records = pd.read_csv(meta, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED if c not in records.columns]
    if missing:
        raise ValueError(f"{meta} is missing columns {missing}")

    rows = []
    for line, record in enumerate(records.itertuples(index=False), start=2):
        where = f"{meta} line {line}"
        if record.label not in LABELS:
            raise ValueError(f"{where}: label must be bonafide or spoof")
        if record.split not in SPLITS:
            raise ValueError(f"{where}: split must be dev or test (team audio is never trained on)")
        if record.label == BONAFIDE and record.attack_type:
            raise ValueError(f"{where}: a bonafide clip has no attack_type")
        if record.label != BONAFIDE and record.attack_type not in ATTACK_TYPES:
            raise ValueError(f"{where}: attack_type must be one of {sorted(ATTACK_TYPES)}")
        rows.append({
            "utt_id": f"{NAME}/{Path(record.file).with_suffix('').as_posix()}",
            "path": Path(record.file).as_posix(),
            "source": NAME,
            "speaker_id": f"{NAME}/{record.speaker_id}",
            "label": record.label,
            "attack_type": record.attack_type,
            "split": record.split,
            "license": LICENSE,
        })
    return rows
