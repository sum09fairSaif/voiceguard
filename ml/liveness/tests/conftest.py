from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def write_tone(path: Path, seconds=2.0, rate=16000, level=0.5, fmt=None):
    """A sine tone, so the tests need no real recordings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(seconds * rate)) / rate
    sf.write(str(path), level * np.sin(2 * np.pi * 220 * t), rate, format=fmt)


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def asvspoof(data_dir):
    """A miniature ASVspoof 2019 LA, laid out like the real LA.zip."""
    la = data_dir / "raw" / "asvspoof2019_la" / "LA"
    protocols = la / "ASVspoof2019_LA_cm_protocols"
    protocols.mkdir(parents=True)
    lines = {
        "train": ("ASVspoof2019.LA.cm.train.trn.txt", [
            "LA_0079 LA_T_0000001 - - bonafide",
            "LA_0079 LA_T_0000002 - A01 spoof",
        ]),
        "dev": ("ASVspoof2019.LA.cm.dev.trl.txt", [
            "LA_0069 LA_D_0000001 - - bonafide",
        ]),
        "eval": ("ASVspoof2019.LA.cm.eval.trl.txt", [
            "LA_0039 LA_E_0000001 - A13 spoof",
            "",
        ]),
    }
    for split, (protocol, rows) in lines.items():
        (protocols / protocol).write_text("\n".join(rows) + "\n")
        for row in rows:
            if row:
                clip = row.split()[1]
                write_tone(la / f"ASVspoof2019_LA_{split}" / "flac" / f"{clip}.flac")
    return data_dir / "raw" / "asvspoof2019_la"


@pytest.fixture
def team_dir(data_dir):
    root = data_dir / "raw" / "team"
    root.mkdir(parents=True)
    (root / "metadata.csv").write_text(
        "file,speaker_id,label,attack_type,split\n"
        "spk01/live_01.wav,spk01,bonafide,,dev\n"
        "spk01/replay_01.wav,spk01,spoof,replay,dev\n"
    )
    write_tone(root / "spk01" / "live_01.wav")
    write_tone(root / "spk01" / "replay_01.wav", seconds=3.0)
    return root
