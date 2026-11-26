"""ASVspoof 2017 (version 2): real replay attacks.

Unlike ASVspoof 2019 PA, whose replays are simulated, these were physically
replayed: RedDots speakers' phrases played through real loudspeakers,
laptops and phones in real rooms and recorded again on real devices (26
playback and 25 recording devices in all). That's what an attacker holding
a recording of our user would do, and what our team replays did, so it's
the closest public data to the attack the liveness check sees most.

The official train, dev and eval splits are kept (eval becomes test). Every
spoof is a replay; the protocol's environment, playback and recording
device columns aren't needed.

Licence: CC BY-NC 4.0, non-commercial use only, unlike the other training
sets. VoiceGuard is a non-commercial student project; if that changes, a
model trained with this dataset has to be retrained without it.

Download DS_10283_3055.zip from https://datashare.ed.ac.uk/handle/10283/3055
into data/raw/asvspoof2017/ and unzip it there, then unzip the
ASVspoof2017_V2_*.zip files it holds in the same folder, so that it has
ASVspoof2017_V2_train/, _dev/, _eval/ and protocol_V2/.
"""

from pathlib import Path

NAME = "asvspoof2017"
LICENSE = "CC-BY-NC-4.0"
# Each split's protocol file and its audio folder.
SPLITS = {
    "train": ("ASVspoof2017_V2_train.trn.txt", "ASVspoof2017_V2_train"),
    "dev": ("ASVspoof2017_V2_dev.trl.txt", "ASVspoof2017_V2_dev"),
    "test": ("ASVspoof2017_V2_eval.trl.txt", "ASVspoof2017_V2_eval"),
}
LABELS = {"genuine": "bonafide", "spoof": "spoof"}


def find_one(root: Path, name: str, directory: bool) -> Path:
    hits = [p for p in root.rglob(name) if p.is_dir() == directory]
    if not hits:
        raise FileNotFoundError(f"{name} not found under {root}; see sources/asvspoof2017.py for how to download it")
    return min(hits, key=lambda p: len(p.parts))


def load(root: Path) -> list[dict]:
    rows = []
    for split, (protocol_name, audio_name) in SPLITS.items():
        protocol = find_one(root, protocol_name, directory=False)
        audio_dir = find_one(root, audio_name, directory=True)
        for line_no, line in enumerate(protocol.read_text(encoding="utf-8").splitlines(), start=1):
            fields = line.split()
            if not fields:
                continue
            if len(fields) < 3 or fields[1] not in LABELS:
                raise ValueError(f"{protocol} line {line_no}: expected '<file> genuine|spoof <speaker> ...'")
            file, label, speaker = fields[0], LABELS[fields[1]], fields[2]
            rows.append({
                "utt_id": f"{NAME}/{Path(file).stem}",
                "path": (audio_dir / file).relative_to(root).as_posix(),
                "source": NAME,
                "speaker_id": f"{NAME}/{speaker}",
                "label": label,
                "attack_type": "replay" if label == "spoof" else "",
                "split": split,
                "license": LICENSE,
            })
    return rows
