import shutil

import pandas as pd
import pytest

import manifest
from build_manifest import build
from conftest import write_tone
from validate import validate, write_report


@pytest.fixture
def built(data_dir, asvspoof, team_dir):
    df = build(data_dir, ["asvspoof2019_la", "team"], workers=2)
    manifest.save(df, data_dir / "manifest.parquet")
    return df


def test_build_describes_every_clip(built):
    assert len(built) == 6
    assert list(built.columns) == manifest.COLUMNS
    assert built["path"].str.startswith(("raw/asvspoof2019_la/", "raw/team/")).all()

    replay = built.set_index("utt_id").loc["team/spk01/replay_01"]
    assert replay["duration_s"] == pytest.approx(3.0)
    assert (replay["sample_rate"], replay["channels"], replay["format"]) == (16000, 1, "WAV")
    assert len(replay["sha256"]) == 64


def test_build_leaves_blanks_for_a_missing_file(data_dir, asvspoof, team_dir):
    (team_dir / "spk01" / "live_01.wav").unlink()
    df = build(data_dir, ["team"], workers=1).set_index("utt_id")
    assert df.loc["team/spk01/live_01", "sha256"] == ""
    assert pd.isna(df.loc["team/spk01/live_01", "duration_s"])


def test_build_refuses_repeated_ids(data_dir, team_dir):
    with open(team_dir / "metadata.csv", "a") as f:
        f.write("spk01/live_01.wav,spk01,bonafide,,dev\n")
    with pytest.raises(ValueError, match="not unique"):
        build(data_dir, ["team"], workers=1)


def test_validate_flags_bad_clips(data_dir, asvspoof, team_dir):
    la = asvspoof / "LA"
    write_tone(la / "ASVspoof2019_LA_train/flac/LA_T_0000001.flac", seconds=0.5)  # too short
    write_tone(la / "ASVspoof2019_LA_train/flac/LA_T_0000002.flac", level=0.001)  # silent
    write_tone(la / "ASVspoof2019_LA_dev/flac/LA_D_0000001.flac", level=5.0)  # clipped
    (la / "ASVspoof2019_LA_eval/flac/LA_E_0000001.flac").write_bytes(b"not audio")
    (team_dir / "spk01" / "live_01.wav").unlink()

    df = build(data_dir, ["asvspoof2019_la", "team"], workers=1)
    clean, issues, _ = validate(df, data_dir, workers=1)

    found = dict(zip(issues["utt_id"], issues["issue"]))
    assert found == {
        "asvspoof2019_la/LA_T_0000001": "too_short",
        "asvspoof2019_la/LA_T_0000002": "silent",
        "asvspoof2019_la/LA_D_0000001": "clipped",
        "asvspoof2019_la/LA_E_0000001": "unreadable",
        "team/spk01/live_01": "missing",
    }
    assert list(clean["utt_id"]) == ["team/spk01/replay_01"]


def test_validate_keeps_one_copy_of_a_duplicate(data_dir, team_dir):
    shutil.copy(team_dir / "spk01" / "live_01.wav", team_dir / "spk01" / "live_02.wav")
    with open(team_dir / "metadata.csv", "a") as f:
        f.write("spk01/live_02.wav,spk01,bonafide,,dev\n")

    df = build(data_dir, ["team"], workers=1)
    clean, issues, _ = validate(df, data_dir, workers=1)

    assert list(issues["utt_id"]) == ["team/spk01/live_02"]
    assert list(issues["issue"]) == ["duplicate"]
    assert "team/spk01/live_01" in set(clean["utt_id"])


def test_validate_drops_duplicates_that_disagree(data_dir, team_dir):
    # The same audio labelled both bonafide and spoof: neither copy can be trusted.
    shutil.copy(team_dir / "spk01" / "live_01.wav", team_dir / "spk01" / "fake.wav")
    with open(team_dir / "metadata.csv", "a") as f:
        f.write("spk01/fake.wav,spk01,spoof,tts,dev\n")

    df = build(data_dir, ["team"], workers=1)
    _, issues, _ = validate(df, data_dir, workers=1)

    assert set(issues["utt_id"]) == {"team/spk01/live_01", "team/spk01/fake"}
    assert set(issues["issue"]) == {"duplicate_conflict"}


def test_report_warns_about_speakers_in_two_splits(data_dir, team_dir):
    write_tone(team_dir / "spk01" / "live_09.wav", seconds=2.5)
    with open(team_dir / "metadata.csv", "a") as f:
        f.write("spk01/live_09.wav,spk01,bonafide,,test\n")

    df = build(data_dir, ["team"], workers=1)
    clean, issues, leaks = validate(df, data_dir, workers=1)
    assert dict(leaks) == {"team/spk01": "dev, test"}

    write_report(df, issues, leaks, data_dir / "report.md")
    report = (data_dir / "report.md").read_text(encoding="utf-8")
    assert "1 speakers appear in more than one split" in report
    assert "| team | dev | 1 | 1 |" in report
