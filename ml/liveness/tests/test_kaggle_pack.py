import base64
import io
import json
import tarfile

import numpy as np
import pandas as pd
import pytest
import soundfile as sf

pytest.importorskip("torch")  # CI doesn't install it (see requirements-model.txt)

import audio  # noqa: E402
import kaggle_pack  # noqa: E402
from training_data import ClipDataset  # noqa: E402


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
    assert "NAME, EPOCHS, MAX_HOURS, RESUME = 'run1', 3, 7.5, True" in script
    assert "elif RESUME:" in script and "sys.exit(" in script
    assert 'f"runs/{NAME}/last.pth"' in script

    code = script.split("CODE = '", 1)[1].split("'", 1)[0]
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(code))) as tar:
        assert set(tar.getnames()) >= {"train.py", "models/aasist.py", "augment.py"}

    meta = json.loads((out / "kernel-metadata.json").read_text())
    assert meta["enable_gpu"] and meta["is_private"]
    assert meta["kernel_sources"] == [f"someone/{kaggle_pack.SCRIPT}"]
