import pytest

import manifest
from sources import asvspoof2019_la, common_voice, in_the_wild, team


def by_id(rows):
    return {row["utt_id"]: row for row in rows}


def test_asvspoof_reads_labels_attacks_and_splits(asvspoof):
    rows = by_id(asvspoof2019_la.load(asvspoof))
    manifest.check_rows(list(rows.values()), "asvspoof2019_la")

    assert len(rows) == 4
    bonafide = rows["asvspoof2019_la/LA_T_0000001"]
    assert bonafide["label"] == "bonafide"
    assert bonafide["attack_type"] == ""
    assert bonafide["speaker_id"] == "asvspoof2019_la/LA_0079"
    assert bonafide["path"] == "LA/ASVspoof2019_LA_train/flac/LA_T_0000001.flac"
    assert (asvspoof / bonafide["path"]).is_file()

    spoof = rows["asvspoof2019_la/LA_T_0000002"]
    assert (spoof["label"], spoof["attack_type"], spoof["split"]) == ("spoof", "A01", "train")
    # The dataset calls it "eval"; the manifest calls it "test".
    assert rows["asvspoof2019_la/LA_E_0000001"]["split"] == "test"


def test_asvspoof_explains_a_missing_download(tmp_path):
    with pytest.raises(FileNotFoundError, match="unzip LA.zip"):
        asvspoof2019_la.load(tmp_path)


def test_in_the_wild_is_test_only(tmp_path):
    folder = tmp_path / "release_in_the_wild"
    folder.mkdir()
    (folder / "meta.csv").write_text(
        "file,speaker,label\n0.wav,Alec Guinness,spoof\n1.wav,Alec Guinness,bona-fide\n"
    )
    rows = by_id(in_the_wild.load(tmp_path))
    manifest.check_rows(list(rows.values()), "in_the_wild")

    assert {row["split"] for row in rows.values()} == {"test"}
    assert rows["in_the_wild/0"]["label"] == "spoof"
    assert rows["in_the_wild/0"]["attack_type"] == "unknown"
    assert rows["in_the_wild/1"]["label"] == "bonafide"
    assert rows["in_the_wild/1"]["path"] == "release_in_the_wild/1.wav"


def test_in_the_wild_refuses_unknown_labels(tmp_path):
    (tmp_path / "meta.csv").write_text("file,speaker,label\n0.wav,Someone,fake\n")
    with pytest.raises(ValueError, match="unknown label"):
        in_the_wild.load(tmp_path)


def test_common_voice_takes_a_few_clips_per_speaker(tmp_path, monkeypatch):
    folder = tmp_path / "cv-corpus-20.0-2024-12-06" / "en"
    folder.mkdir(parents=True)
    header = "client_id\tpath\tsentence\n"
    # A sentence with an unmatched quote mark mustn't break parsing.
    many = "".join(f"aaa\tcommon_voice_en_{i}.mp3\tShe said \"hi.\n" for i in range(8))
    (folder / "train.tsv").write_text(header + many + "bbb\tcommon_voice_en_99.mp3\tHello.\n")
    (folder / "dev.tsv").write_text(header + "ccc\tcommon_voice_en_50.mp3\tYes.\n")
    (folder / "test.tsv").write_text(header)
    monkeypatch.setattr(common_voice, "CLIPS_PER_SPEAKER", 3)

    rows = common_voice.load(tmp_path)
    manifest.check_rows(rows, "common_voice")

    train = [r for r in rows if r["split"] == "train"]
    assert sum(r["speaker_id"] == "common_voice/aaa" for r in train) == 3
    assert sum(r["speaker_id"] == "common_voice/bbb" for r in train) == 1
    assert {r["label"] for r in rows} == {"bonafide"}
    assert train[0]["path"].startswith("cv-corpus-20.0-2024-12-06/en/clips/")
    assert [r["split"] for r in rows].count("dev") == 1


def test_team_reads_metadata(team_dir):
    rows = by_id(team.load(team_dir))
    manifest.check_rows(list(rows.values()), "team")
    replay = rows["team/spk01/replay_01"]
    assert (replay["label"], replay["attack_type"], replay["split"]) == ("spoof", "replay", "dev")
    assert replay["path"] == "spk01/replay_01.wav"


@pytest.mark.parametrize("line, message", [
    ("a.wav,spk01,bonafide,replay,dev", "bonafide clip has no attack_type"),
    ("a.wav,spk01,spoof,,dev", "attack_type must be one of"),
    ("a.wav,spk01,spoof,replay,train", "never trained on"),
    ("a.wav,spk01,fake,,dev", "bonafide or spoof"),
])
def test_team_refuses_bad_metadata(tmp_path, line, message):
    (tmp_path / "metadata.csv").write_text("file,speaker_id,label,attack_type,split\n" + line + "\n")
    with pytest.raises(ValueError, match=message):
        team.load(tmp_path)
