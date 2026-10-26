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

# The dataset's split names, mapped to ours, with each split's protocol file
# (the list of clips and their labels).
SPLITS = {
    "train": ("train", "ASVspoof2019.LA.cm.train.trn.txt"),
    "dev": ("dev", "ASVspoof2019.LA.cm.dev.trl.txt"),
    "eval": ("test", "ASVspoof2019.LA.cm.eval.trl.txt"),
}


def load(root: Path) -> list[dict]:
    la = root / "LA" if (root / "LA").is_dir() else root
    protocols = la / "ASVspoof2019_LA_cm_protocols"
    if not protocols.is_dir():
        raise FileNotFoundError(f"{protocols} not found; unzip LA.zip into {root}")
    prefix = la.relative_to(root)  # "LA", or "." if root is the LA folder itself

    rows = []
    for their_split, (our_split, protocol) in SPLITS.items():
        # Each line: speaker, clip name, "-", attack system ("-" if bonafide), label.
        # e.g. "LA_0079 LA_T_1138215 - - bonafide"
        for line in (protocols / protocol).read_text().splitlines():
            if not line.strip():
                continue
            speaker, clip, _, system, key = line.split()
            label = BONAFIDE if key == "bonafide" else SPOOF
            rows.append({
                "utt_id": f"{NAME}/{clip}",
                "path": (prefix / f"ASVspoof2019_LA_{their_split}" / "flac" / f"{clip}.flac").as_posix(),
                "source": NAME,
                "speaker_id": f"{NAME}/{speaker}",
                "label": label,
                "attack_type": system if label == SPOOF else "",
                "split": our_split,
                "license": LICENSE,
            })
    return rows
