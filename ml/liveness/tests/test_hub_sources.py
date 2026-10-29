"""Loaders for the datasets fetched by download.py, on miniature copies of their layouts."""

import pytest

import manifest
from sources import asvspoof5, codecfake


def by_id(rows):
    return {row["utt_id"]: row for row in rows}


@pytest.fixture
def asvspoof5_dir(tmp_path):
    (tmp_path / "ASVspoof5.train.tsv").write_text("T_0001 T_0000000001 F - - - AC1 A01 spoof -\n")
    (tmp_path / "ASVspoof5.dev.track_1.tsv").write_text(
        "D_0001 D_0000000001 F - - - - bonafide bonafide -\n"
        "D_0002 D_0000000002 M - - - AC2 A11 spoof -\n"
    )
    (tmp_path / "ASVspoof5.eval.track_1.tsv").write_text(
        "E_0001 E_0000000001 M C05 2 E_0000000009 AC1 A26 spoof -\n"
        "E_0002 E_0000000002 F - 0 - - bonafide bonafide -\n"
    )
    for folder, clip in [("flac_D", "D_0000000001"), ("flac_D", "D_0000000002"), ("flac_E_eval", "E_0000000001")]:
        (tmp_path / folder).mkdir(exist_ok=True)
        (tmp_path / folder / f"{clip}.flac").write_bytes(b"")
    return tmp_path


def test_asvspoof5_keeps_only_downloaded_clips(asvspoof5_dir):
    rows = by_id(asvspoof5.load(asvspoof5_dir))
    manifest.check_rows(list(rows.values()), "asvspoof5")

    # Train wasn't downloaded, and E_0000000002's eval part wasn't either.
    assert set(rows) == {"asvspoof5/D_0000000001", "asvspoof5/D_0000000002", "asvspoof5/E_0000000001"}
    assert rows["asvspoof5/D_0000000001"]["label"] == "bonafide"
    assert rows["asvspoof5/D_0000000001"]["attack_type"] == ""
    spoof = rows["asvspoof5/E_0000000001"]
    assert (spoof["label"], spoof["attack_type"], spoof["split"]) == ("spoof", "A26", "test")
    assert spoof["path"] == "flac_E_eval/E_0000000001.flac"
    assert spoof["speaker_id"] == "asvspoof5/E_0001"


def test_asvspoof5_explains_a_missing_download(tmp_path):
    with pytest.raises(FileNotFoundError, match="download.py asvspoof5"):
        asvspoof5.load(tmp_path)


def test_codecfake_labels_and_speaker_splits(tmp_path):
    (tmp_path / "metadata.csv").write_text(
        "file,label,speaker_id,codec,shard\n"
        "audio/genuine/p225_001.wav,genuine,p225,genuine,s45\n"
        "audio/encodec_24khz/p225_001.wav,spoofing,p225,encodec_24khz,s85\n"
        "audio/encodec_24khz/p226_002.wav,spoofing,p226,encodec_24khz,s85\n"
    )
    rows = by_id(codecfake.load(tmp_path))
    manifest.check_rows(list(rows.values()), "codecfake")

    real = rows["codecfake/audio/genuine/p225_001"]
    fake = rows["codecfake/audio/encodec_24khz/p225_001"]
    assert (real["label"], real["attack_type"]) == ("bonafide", "")
    assert (fake["label"], fake["attack_type"]) == ("spoof", "encodec_24khz")
    # A speaker's real and fake clips always land in the same split.
    assert real["split"] == fake["split"] == codecfake.speaker_split("p225")


def test_codecfake_split_is_roughly_80_10_10():
    splits = [codecfake.speaker_split(f"p{n}") for n in range(1000)]
    assert 700 < splits.count("train") < 900
    assert 50 < splits.count("test") < 150

