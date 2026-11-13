import base64
import io
import json
import tarfile

import numpy as np
import pandas as pd
import pytest
import soundfile as sf

pytest.importorskip("torch")  # CI doesn't install it (see requirements-model.txt)

import audio
import kaggle_pack
from training_data import ClipDataset


@pytest.fixture
def processed(tmp_path):
    """A tiny processed data folder: 3 sources, some clips over 5 seconds."""
    rng = np.random.default_rng(0)
    rows = []
    groups = [("big", "spoof", 12, 8.0), ("big", "bonafide", 3, 7.0), ("small", "spoof", 4, 2.0),
              ("small", "bonafide", 2, 3.0)]
    for split in ["train", "dev", "test"]:
        for source, label, n, seconds in groups:
            for i in range(n):
                path = f"processed/{source}/{split}_{label}_{i}.flac"
                (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(tmp_path / path), (0.05 * rng.standard_normal(int(seconds * 16000))).astype(np.float32),
                         16000, subtype="PCM_16")
                rows.append({"utt_id": f"{source}/{split}_{label}_{i}", "path": path, "source": source,
                             "speaker_id": f"{source}/s{i % 2}", "label": label, "split": split,
                             "attack_type": f"A{i % 3}" if label == "spoof" else "", "duration_s": seconds})
    pd.DataFrame(rows).to_parquet(tmp_path / "manifest.processed.parquet")
    weights = tmp_path / kaggle_pack.WEIGHTS_SOURCE
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"weights")
    return tmp_path


def test_big_groups_are_thinned_evenly_and_test_is_left_out(processed, monkeypatch):
    monkeypatch.setattr(kaggle_pack, "MAX_PER_GROUP", 6)
    clips = kaggle_pack.choose_clips(processed)
    train = clips[clips["split"] == "train"]
    assert train.groupby(["source", "label"]).size().to_dict() == {
        ("big", "bonafide"): 3, ("big", "spoof"): 6, ("small", "bonafide"): 2, ("small", "spoof"): 4}
    assert train.loc[train["source"] == "big"].query("label == 'spoof'")["attack_type"].value_counts().to_dict() == {
        "A0": 2, "A1": 2, "A2": 2}
    assert set(clips["split"]) == {"train", "dev"}


def test_the_pack_reads_back_clip_for_clip(processed, monkeypatch):
    monkeypatch.setattr(kaggle_pack, "SHARD_BYTES", 400_000)  # force several shards
    out = processed / "kaggle" / "data"
    kaggle_pack.write_data(processed, out, workers=1)
    kaggle_pack.write_dataset_metadata(out, "someone")

    index = pd.read_parquet(out / "manifest.processed.parquet")
    assert index["shard"].nunique() > 1
    assert (out / kaggle_pack.WEIGHTS).read_bytes() == b"weights"
    assert json.loads((out / "dataset-metadata.json").read_text())["id"] == f"someone/{kaggle_pack.DATASET}"
    # Long clips are cut to 5 seconds; short ones are the same file.
    assert index["duration_s"].max() == kaggle_pack.MAX_SECONDS

    packed = ClipDataset(index, out)
    original = pd.read_parquet(processed / "manifest.processed.parquet").set_index("utt_id")
    for i, utt_id in enumerate(index["utt_id"]):
        samples = packed.read(i)
        source, _ = sf.read(str(processed / original.loc[utt_id, "path"]), dtype="float32")
        assert np.array_equal(samples, source[: len(samples)])
        assert len(samples) == min(len(source), int(kaggle_pack.MAX_SECONDS * audio.TARGET_RATE))


def test_the_script_carries_the_code_and_the_settings(processed, tmp_path):
    out = tmp_path / "script"
    kaggle_pack.write_script(kaggle_pack.Path(kaggle_pack.__file__).parent, out, "someone", "run1", 3, 7.5,
                             resume=True)
    script = (out / "run.py").read_text(encoding="utf-8")
    compile(script, "run.py", "exec")
    assert "NAME, EPOCHS, MAX_HOURS, RESUME, NOISE = 'run1', 3, 7.5, True, False" in script
    assert "elif RESUME:" in script and "sys.exit(" in script
    assert 'f"runs/{NAME}/last.pth"' in script

    code = script.split("CODE = '", 1)[1].split("'", 1)[0]
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(code))) as tar:
        assert set(tar.getnames()) >= {"train.py", "models/aasist.py", "augment.py"}

    meta = json.loads((out / "kernel-metadata.json").read_text())
    assert meta["enable_gpu"] and meta["is_private"]
    assert meta["kernel_sources"] == [f"someone/{kaggle_pack.SCRIPT}"]
    assert meta["dataset_sources"] == [f"someone/{kaggle_pack.DATASET}"]


def test_a_noise_run_attaches_the_noise_dataset_and_insists_on_it(tmp_path):
    out = tmp_path / "script"
    kaggle_pack.write_script(kaggle_pack.Path(kaggle_pack.__file__).parent, out, "someone", "run1", 3, 7.5,
                             resume=False, noise=True)
    script = (out / "run.py").read_text(encoding="utf-8")
    compile(script, "run.py", "exec")
    assert "NAME, EPOCHS, MAX_HOURS, RESUME, NOISE = 'run1', 3, 7.5, False, True" in script
    assert "if NOISE and not noise:" in script
    meta = json.loads((out / "kernel-metadata.json").read_text())
    assert meta["dataset_sources"] == [f"someone/{kaggle_pack.DATASET}", f"someone/{kaggle_pack.NOISE_DATASET}"]


def test_the_noise_pack_holds_every_echo_and_noise(tmp_path):
    noise = tmp_path / kaggle_pack.NOISE_SOURCE
    files = ["simulated_rirs/smallroom/Room001/Room001-00001.wav", "pointsource_noises/noise-free-sound-0001.wav",
             "real_rirs_isotropic_noises/air_type1_air_binaural_lecture_0_1.wav"]
    for name in files:
        (noise / name).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(noise / name), np.zeros(160, dtype=np.float32), 16000)
    out = tmp_path / "kaggle" / "noise"

    assert kaggle_pack.write_noise(tmp_path, out)
    kaggle_pack.write_noise_metadata(out, "someone")

    with tarfile.open(out / "rirs_noises.tar") as tar:
        assert {f"RIRS_NOISES/{name}" for name in files} <= set(tar.getnames())
    assert json.loads((out / "dataset-metadata.json").read_text())["id"] == f"someone/{kaggle_pack.NOISE_DATASET}"


def test_no_noise_downloaded_means_no_noise_pack(tmp_path):
    assert not kaggle_pack.write_noise(tmp_path, tmp_path / "kaggle" / "noise")
    assert not (tmp_path / "kaggle" / "noise").exists()
