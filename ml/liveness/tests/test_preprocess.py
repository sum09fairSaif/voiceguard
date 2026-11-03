import numpy as np
import pandas as pd
import pytest
import soundfile as sf

import audio
import manifest
from build_manifest import build
from conftest import write_tone
from preprocess import OUT_FOLDER, collect, processed_path, run_jobs, write_report


def tone(seconds, level=0.1, rate=audio.TARGET_RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (level * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def stereo(samples):
    return np.column_stack([samples, samples])


def rms(samples):
    return float(np.sqrt(np.mean(samples**2)))


def speech_with_silence(lead, speech, tail, level=0.1):
    rate = audio.TARGET_RATE
    return np.concatenate([np.zeros(int(lead * rate), np.float32), tone(speech, level),
                           np.zeros(int(tail * rate), np.float32)])


@pytest.mark.parametrize("rate", [16000, 24000, 44100, 48000])
def test_every_rate_comes_out_as_16k_mono(rate):
    mono = audio.to_mono_16k(stereo(tone(2.0, rate=rate)), rate)
    assert mono.ndim == 1
    assert len(mono) == pytest.approx(2 * audio.TARGET_RATE, abs=2)


def test_trim_removes_all_the_silence_at_both_ends():
    start, end = audio.speech_bounds(speech_with_silence(1.0, 2.0, 0.5))
    assert start / audio.TARGET_RATE == pytest.approx(1.0, abs=0.03)
    assert end / audio.TARGET_RATE == pytest.approx(3.0, abs=0.03)


def test_background_noise_counts_as_silence():
    rng = np.random.default_rng(0)

    def noise(seconds):
        return 0.0015 * rng.standard_normal(int(seconds * audio.TARGET_RATE)).astype(np.float32)

    samples = np.concatenate([noise(1.0), tone(2.0), noise(1.0)])
    start, end = audio.speech_bounds(samples)
    assert start / audio.TARGET_RATE == pytest.approx(1.0, abs=0.03)
    assert end / audio.TARGET_RATE == pytest.approx(3.0, abs=0.05)


def test_dc_offset_is_removed():
    cleaned, _ = audio.clean(stereo(tone(2.0) + 0.05), audio.TARGET_RATE)
    assert abs(cleaned.mean()) < 1e-3


def test_dc_offset_doesnt_pass_for_sound():
    samples = speech_with_silence(1.0, 2.0, 1.0) + 0.05
    cleaned, _ = audio.clean(stereo(samples), audio.TARGET_RATE)
    assert len(cleaned) / audio.TARGET_RATE < 2.2


def test_trim_keeps_pauses_inside_the_speech():
    samples = np.concatenate([tone(1.0), np.zeros(audio.TARGET_RATE, np.float32), tone(1.0)])
    start, end = audio.speech_bounds(samples)
    assert (end - start) / audio.TARGET_RATE == pytest.approx(3.0, abs=0.05)


def test_quiet_and_loud_clips_end_up_equally_loud():
    quiet, _ = audio.clean(stereo(tone(2.0, level=0.02)), audio.TARGET_RATE)
    loud, _ = audio.clean(stereo(tone(2.0, level=0.5)), audio.TARGET_RATE)
    assert rms(quiet) == pytest.approx(rms(loud), rel=0.01)
    assert 20 * np.log10(rms(quiet)) == pytest.approx(audio.TARGET_DBFS, abs=0.5)


def test_loudness_ignores_how_much_silence_a_clip_had():
    plain, _ = audio.clean(stereo(tone(2.0)), audio.TARGET_RATE)
    padded, _ = audio.clean(stereo(speech_with_silence(3.0, 2.0, 3.0)), audio.TARGET_RATE)
    assert np.abs(plain).max() == pytest.approx(np.abs(padded).max(), rel=0.02)


def test_a_click_cannot_push_a_clip_past_full_scale():
    samples = tone(2.0, level=0.01)
    samples[1000] = 0.9
    cleaned, _ = audio.clean(stereo(samples), audio.TARGET_RATE)
    assert np.abs(cleaned).max() <= audio.MAX_PEAK + 1e-6


def test_a_silent_clip_comes_back_empty():
    cleaned, _ = audio.clean(np.zeros((16000, 1), np.float32), audio.TARGET_RATE)
    assert len(cleaned) == 0


def test_fix_length_repeats_short_clips():
    samples = np.arange(40000, dtype=np.float32)
    fixed = audio.fix_length(samples)
    assert len(fixed) == audio.CROP_SAMPLES
    assert fixed[40000] == 0


def test_fix_length_takes_the_start_when_scoring_and_varies_when_training():
    samples = np.arange(200000, dtype=np.float32)
    assert audio.fix_length(samples)[0] == 0
    rng = np.random.default_rng(0)
    crops = [audio.fix_length(samples, rng) for _ in range(5)]
    assert all(len(c) == audio.CROP_SAMPLES for c in crops)
    assert len({float(c[0]) for c in crops}) > 1


def test_processed_path_mirrors_raw():
    assert processed_path("raw/common_voice/cv/a.mp3") == f"{OUT_FOLDER}/common_voice/cv/a.flac"


@pytest.fixture
def built(data_dir, team_dir):
    write_tone(team_dir / "spk01" / "hi_rate.wav", seconds=2.0, rate=44100)
    with open(team_dir / "metadata.csv", "a") as f:
        f.write("spk01/hi_rate.wav,spk01,spoof,tts,dev\n")
    return build(data_dir, ["team"], workers=1)


def test_run_writes_clips_and_a_manifest(data_dir, built):
    run_jobs(built, data_dir, workers=1)
    kept, issues = collect(built, data_dir)

    assert len(kept) == 3 and issues.empty
    assert list(kept.columns[: len(manifest.COLUMNS)]) == manifest.COLUMNS
    assert set(kept["sample_rate"]) == {16000} and set(kept["format"]) == {"FLAC"}

    clip = kept.set_index("utt_id").loc["team/spk01/hi_rate"]
    info = sf.info(str(data_dir / clip["path"]))
    assert (info.samplerate, info.channels) == (16000, 1)
    assert clip["raw_path"] == "raw/team/spk01/hi_rate.wav"
    assert clip["duration_s"] == pytest.approx(info.frames / info.samplerate)

    kept.to_parquet(data_dir / "out.parquet", index=False)
    assert len(manifest.load(data_dir / "out.parquet")) == 3


def test_a_rerun_only_does_the_unfinished_clips(data_dir, built, capsys):
    run_jobs(built.iloc[:2], data_dir, workers=1)
    run_jobs(built, data_dir, workers=1)
    assert "2 clips already done, 1 to do" in capsys.readouterr().out
    assert len(pd.read_csv(data_dir / OUT_FOLDER / "progress.csv")) == 3


def test_a_rerun_recovers_from_a_half_written_row(data_dir, built, capsys):
    run_jobs(built, data_dir, workers=1)
    progress = data_dir / OUT_FOLDER / "progress.csv"
    lines = progress.read_bytes().splitlines(keepends=True)
    progress.write_bytes(b"".join(lines[:-1]) + lines[-1][:15])  # killed mid-row

    run_jobs(built, data_dir, workers=1)

    assert "2 clips already done, 1 to do" in capsys.readouterr().out
    assert sorted(pd.read_csv(progress)["utt_id"]) == sorted(built["utt_id"])


def test_mostly_silent_clip_is_dropped_after_trimming(data_dir, team_dir):
    samples = speech_with_silence(1.0, 0.3, 1.0)
    sf.write(str(team_dir / "spk01" / "live_01.wav"), samples, audio.TARGET_RATE)
    df = build(data_dir, ["team"], workers=1)

    run_jobs(df, data_dir, workers=1)
    kept, issues = collect(df, data_dir)

    assert dict(zip(issues["utt_id"], issues["issue"])) == {"team/spk01/live_01": "too_short_after_trim"}
    assert list(kept["utt_id"]) == ["team/spk01/replay_01"]


def test_a_corrupt_clip_is_dropped(data_dir, team_dir):
    samples = tone(2.0)
    samples[1000] = 2300.0  # possible only in a damaged file
    sf.write(str(team_dir / "spk01" / "live_01.wav"), samples, audio.TARGET_RATE, subtype="FLOAT")
    df = build(data_dir, ["team"], workers=1)

    run_jobs(df, data_dir, workers=1)
    kept, issues = collect(df, data_dir)

    assert dict(zip(issues["utt_id"], issues["issue"])) == {"team/spk01/live_01": "corrupt"}
    assert list(kept["utt_id"]) == ["team/spk01/replay_01"]


def test_changed_settings_are_refused(data_dir, built, monkeypatch):
    run_jobs(built.iloc[:1], data_dir, workers=1)
    monkeypatch.setitem(__import__("preprocess").SETTINGS, "TRIM_DB", 99)
    with pytest.raises(SystemExit, match="settings changed"):
        run_jobs(built, data_dir, workers=1)


def test_report_compares_real_and_fake(data_dir, built):
    run_jobs(built, data_dir, workers=1)
    kept, issues = collect(built, data_dir)
    write_report(built, kept, issues, data_dir / "report.md")
    report = (data_dir / "report.md").read_text(encoding="utf-8")
    assert "| team | bonafide | 1 |" in report and "| team | spoof | 2 |" in report
