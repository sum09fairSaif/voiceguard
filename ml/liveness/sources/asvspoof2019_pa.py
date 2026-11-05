"""ASVspoof 2019 Physical Access (PA): replay attacks.

An attacker records the user and plays the recording back to the
microphone. This is the only replay data we have; the other datasets are
all AI-generated speech.

The replays are simulated, not physically recorded: the bonafide speech
(VCTK) is put through models of 27 rooms and 9 attack setups. Each attack
code is two letters: how far the attacker's microphone was from the talker
(A: 10-50 cm, B: 50-100 cm, C: over 1 m), then the replay device's quality
(A: perfect, B: high, C: low). The room is in the protocol's third column.
Real recorded replays (like ours, played through a phone speaker) may sound
different, which is why the team recordings matter.

The official train, dev and eval splits are kept; they have no speakers in
common. Like LA, the speech is VCTK, so the same people appear in LA, PA
and CodecFake under different ids.

If you have the Kaggle copy of ASVspoof 2019 (LA and PA in one zip),
extract its PA/PA/ folder into data/raw/asvspoof2019_pa/PA/. Otherwise
download PA.zip from https://datashare.ed.ac.uk/handle/10283/3336 and unzip
it into data/raw/asvspoof2019_pa/, so that folder holds PA/.
"""

from pathlib import Path

from sources.asvspoof2019_la import read_protocols

NAME = "asvspoof2019_pa"
LICENSE = "ODC-By-1.0"


def load(root: Path) -> list[dict]:
    return read_protocols(root, "PA", NAME, LICENSE)
