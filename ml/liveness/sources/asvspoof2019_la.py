"""ASVspoof 2019 Logical Access (LA): the standard anti-spoofing benchmark.

Bonafide speech (from the VCTK corpus) plus spoofs made by 19 different
text-to-speech and voice-conversion systems, labelled A01 to A19. The
pretrained AASIST weights were trained on this set, so it's where we
check that our pipeline reproduces the published accuracy.

The official train, dev and eval splits are kept as they are: they have no
speakers in common, and eval uses attack systems the train split never saw.

Download LA.zip from https://datashare.ed.ac.uk/handle/10283/3336 and unzip
it into data/raw/asvspoof2019_la/, so that folder holds LA/.
"""

from pathlib import Path

from manifest import BONAFIDE, SPOOF

NAME = "asvspoof2019_la"
LICENSE = "ODC-By-1.0"

# The dataset's split names, mapped to ours.
SPLITS = {"train": "train", "dev": "dev", "eval": "test"}
# Each split's protocol file (the list of clips and their labels).
PROTOCOLS = {"train": "trn", "dev": "trl", "eval": "trl"}


def read_protocols(root: Path, part: str, name: str, license_name: str) -> list[dict]:
    """Rows for one half of ASVspoof 2019: part is "LA" or "PA".

    Both halves have the same layout and the same five protocol columns.
    """
    folder = root / part if (root / part).is_dir() else root
    protocols = folder / f"ASVspoof2019_{part}_cm_protocols"
    if not protocols.is_dir():
        raise FileNotFoundError(f"{protocols} not found; unzip {part}.zip into {root}")
    prefix = folder.relative_to(root)  # e.g. "LA", or "." if root is that folder itself

    rows = []
    for their_split, our_split in SPLITS.items():
        protocol = protocols / f"ASVspoof2019.{part}.cm.{their_split}.{PROTOCOLS[their_split]}.txt"
        # Each line: speaker, clip name, a third column, attack ("-" if bonafide), label.
        # e.g. "LA_0079 LA_T_1138215 - - bonafide" or "PA_0079 PA_T_0000010 aaa AA spoof"
        for line in protocol.read_text().splitlines():
            if not line.strip():
                continue
            speaker, clip, _, attack, key = line.split()
            label = BONAFIDE if key == "bonafide" else SPOOF
            rows.append({
                "utt_id": f"{name}/{clip}",
                "path": (prefix / f"ASVspoof2019_{part}_{their_split}" / "flac" / f"{clip}.flac").as_posix(),
                "source": name,
                "speaker_id": f"{name}/{speaker}",
                "label": label,
                "attack_type": attack if label == SPOOF else "",
                "split": our_split,
                "license": license_name,
            })
    return rows


def load(root: Path) -> list[dict]:
    return read_protocols(root, "LA", NAME, LICENSE)
