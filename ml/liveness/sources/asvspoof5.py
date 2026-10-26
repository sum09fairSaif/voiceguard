"""ASVspoof 5 (2024): the newest ASVspoof, much closer to real-world audio.

About 2,000 crowdsourced speakers recorded in varied conditions (unlike
2019's studio speech), 32 attacks from modern TTS and voice conversion,
some adversarial (built to fool detectors). Most eval clips have also been
through a codec or compressor (C01 to C11), which is useful for checking
liveness on compressed audio. The protocol files keep those details
(CODEC, CODEC_Q) for later analysis.

Official splits are kept: train, dev and eval have no speakers in common,
and eval's attacks (A17 to A32) never appear in train or dev.

The full dataset is 143 GB, so `python download.py asvspoof5` takes dev and
part of eval. Clips in the protocols but not downloaded are skipped.
"""

import os
from pathlib import Path

from manifest import BONAFIDE, SPOOF

NAME = "asvspoof5"
LICENSE = "ODC-By-1.0 (bonafide audio CC-BY-4.0)"

# Protocol file, the folder its audio unpacks to, and our split name.
SPLITS = [
    ("ASVspoof5.train.tsv", "flac_T", "train"),
    ("ASVspoof5.dev.track_1.tsv", "flac_D", "dev"),
    ("ASVspoof5.eval.track_1.tsv", "flac_E_eval", "test"),
]


def load(root: Path) -> list[dict]:
    if not (root / "ASVspoof5.dev.track_1.tsv").is_file():
        raise FileNotFoundError(f"no ASVspoof 5 protocols in {root}; run `python download.py asvspoof5`")

    rows = []
    for protocol, folder, split in SPLITS:
        audio = root / folder
        if not audio.is_dir():
            continue  # this split wasn't downloaded
        present = {entry.name for entry in os.scandir(audio)}
        # Space-separated: SPEAKER_ID FLAC_FILE_NAME GENDER CODEC CODEC_Q
        # CODEC_SEED ATTACK_TAG ATTACK_LABEL KEY TMP
        for line in (root / protocol).read_text().splitlines():
            if not line.strip():
                continue
            speaker, clip, _, _, _, _, _, attack, key, _ = line.split()
            if f"{clip}.flac" not in present:
                continue
            label = BONAFIDE if key == "bonafide" else SPOOF
            rows.append({
                "utt_id": f"{NAME}/{clip}",
                "path": f"{folder}/{clip}.flac",
                "source": NAME,
                "speaker_id": f"{NAME}/{speaker}",
                "label": label,
                "attack_type": attack if label == SPOOF else "",
                "split": split,
                "license": LICENSE,
            })
    return rows
