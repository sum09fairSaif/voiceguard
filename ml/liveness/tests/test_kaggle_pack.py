import base64
import inspect
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
    assert "NAME, EPOCHS, MAX_HOURS, RESUME, NOISE, EXTRA = 'run1', 3, 7.5, True, False, False" in script
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
    assert "NAME, EPOCHS, MAX_HOURS, RESUME, NOISE, EXTRA = 'run1', 3, 7.5, False, True, False" in script
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

    with tarfile.open(out / kaggle_pack.NOISE_PACK) as tar:
        assert {f"RIRS_NOISES/{name}" for name in files} <= set(tar.getnames())
    assert json.loads((out / "dataset-metadata.json").read_text())["id"] == f"someone/{kaggle_pack.NOISE_DATASET}"


def test_no_noise_downloaded_means_no_noise_pack(tmp_path):
    assert not kaggle_pack.write_noise(tmp_path, tmp_path / "kaggle" / "noise")
    assert not (tmp_path / "kaggle" / "noise").exists()


def make_noise(root, files=("simulated_rirs/smallroom/Room001/Room001-00001.wav",
                            "pointsource_noises/noise-free-sound-0001.wav")):
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(root / name), np.zeros(160, dtype=np.float32), 16000)


def test_an_incomplete_download_makes_no_pack(tmp_path):
    # Noises but no room echoes, as after an interrupted copy.
    make_noise(tmp_path / kaggle_pack.NOISE_SOURCE, ["pointsource_noises/noise-free-sound-0001.wav"])

    assert not kaggle_pack.write_noise(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out" / kaggle_pack.NOISE_PACK).exists()


def test_an_old_pack_is_removed_when_the_noise_is_gone(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / kaggle_pack.NOISE_PACK).write_bytes(b"stale")

    assert not kaggle_pack.write_noise(tmp_path, out)
    assert not (out / kaggle_pack.NOISE_PACK).exists()


def test_packing_again_removes_the_old_uncompressed_pack(tmp_path):
    make_noise(tmp_path / kaggle_pack.NOISE_SOURCE)
    out = tmp_path / "out"
    out.mkdir()
    (out / kaggle_pack.OLD_NOISE_PACK).write_bytes(b"old")

    assert kaggle_pack.write_noise(tmp_path, out)
    assert sorted(path.name for path in out.iterdir()) == [kaggle_pack.NOISE_PACK]


def test_an_interrupted_pack_leaves_no_archive_under_the_real_name(tmp_path, monkeypatch):
    make_noise(tmp_path / kaggle_pack.NOISE_SOURCE)
    out = tmp_path / "out"
    out.mkdir()
    (out / kaggle_pack.NOISE_PACK).write_bytes(b"earlier")

    def interrupted(self, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(tarfile.TarFile, "add", interrupted)
    with pytest.raises(KeyboardInterrupt):
        kaggle_pack.write_noise(tmp_path, out)

    # Neither a half-written archive nor the earlier one is left to upload.
    assert list(out.iterdir()) == []


@pytest.mark.parametrize(
    "files, usable",
    [
        (("simulated_rirs/a/b.wav", "pointsource_noises/n.wav"), True),
        (("real_rirs_isotropic_noises/air_rir.wav", "real_rirs_isotropic_noises/air_noise.wav"), True),
        (("pointsource_noises/n.wav",), False),
        (("simulated_rirs/a/b.wav",), False),
        ((), False),
    ],
)
def test_noise_counts_as_usable_only_with_both_echoes_and_noises(tmp_path, files, usable):
    make_noise(tmp_path, files)

    assert kaggle_pack.noise_usable(tmp_path) is usable


def test_the_run_checks_the_noise_the_same_way_before_training():
    # The run can't import kaggle_pack, so it has its own copy of the check.
    lines = [line.strip() for line in inspect.getsource(kaggle_pack.noise_usable).splitlines()]
    logic = [line for line in lines if line.startswith(("real =", "echoes =", "noises =", "return "))]
    script = kaggle_pack.RUN_SCRIPT
    assert len(logic) == 4
    for line in logic:
        assert line in script


def test_the_run_prefers_the_gzipped_noise_pack():
    script = kaggle_pack.RUN_SCRIPT
    assert 'find("rirs_noises.tar.gz") or find("rirs_noises.tar")' in script
    assert script.index("noise_usable(root)]") < script.index('subprocess.run([sys.executable, "train.py"')


def test_kaggle_installs_the_versions_in_requirements(tmp_path):
    out = tmp_path / "script"
    here = kaggle_pack.Path(kaggle_pack.__file__).parent
    kaggle_pack.write_script(here, out, "someone", "run1", 3, 7.5, resume=False)
    script = (out / "run.py").read_text(encoding="utf-8")
    requirements = (here / "requirements.txt").read_text(encoding="utf-8").splitlines()
    for name in kaggle_pack.KAGGLE_INSTALLS:
        pin = next(line.strip() for line in requirements if line.strip().startswith(f"{name}=="))
        assert repr(pin) in script


def test_kaggle_pins_reads_only_what_kaggle_needs(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("# a comment\nnumpy==1.26.4\nsoxr==1.1.0  # resamples\nSoundFile==0.14.0\n"
                            "miniaudio==1.73\n", encoding="utf-8")
    assert kaggle_pack.kaggle_pins(requirements) == ["soxr==1.1.0", "SoundFile==0.14.0", "miniaudio==1.73"]

    requirements.write_text("soxr==1.1.0\nsoundfile>=0.13\n", encoding="utf-8")
    with pytest.raises(ValueError, match="soundfile, miniaudio"):
        kaggle_pack.kaggle_pins(requirements)


def test_an_ssl_run_installs_transformers_and_skips_the_aasist_checkpoint(tmp_path):
    out = tmp_path / "script"
    kaggle_pack.write_script(kaggle_pack.Path(kaggle_pack.__file__).parent, out, "someone", "xlsr", 6, 8.0,
                             resume=False, noise=True, arch="ssl")
    script = (out / "run.py").read_text(encoding="utf-8")
    compile(script, "run.py", "exec")
    assert f"TRAIN_ARGS, EXTRA_PACKAGES = {kaggle_pack.SSL_TRAIN_ARGS!r}, {[kaggle_pack.TRANSFORMERS]!r}" in script
    # The pretrained front end comes from Hugging Face; no AASIST --init.
    assert 'elif "--arch" not in TRAIN_ARGS:' in script
    code = script.split("CODE = '", 1)[1].split("'", 1)[0]
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(code))) as tar:
        assert "models/ssl_aasist.py" in tar.getnames()


def test_an_aasist_run_is_unchanged_by_the_ssl_option(tmp_path):
    out = tmp_path / "script"
    kaggle_pack.write_script(kaggle_pack.Path(kaggle_pack.__file__).parent, out, "someone", "run1", 3, 7.5,
                             resume=False)
    script = (out / "run.py").read_text(encoding="utf-8")
    assert "TRAIN_ARGS, EXTRA_PACKAGES = [], []" in script


def test_an_extra_pack_holds_only_its_datasets(processed):
    out = processed / "kaggle" / "extra"
    kaggle_pack.write_data(processed, out, workers=1, sources=["small"])
    kaggle_pack.write_extra_metadata(out, "someone", ["small"])

    index = pd.read_parquet(out / kaggle_pack.EXTRA_INDEX)
    assert set(index["source"]) == {"small"}
    assert set(index["split"]) == {"train", "dev"}
    assert not (out / kaggle_pack.WEIGHTS).exists()
    assert json.loads((out / "dataset-metadata.json").read_text())["id"] == f"someone/{kaggle_pack.EXTRA_DATASET}"


def test_an_extra_pack_needs_its_datasets_in_the_manifest(processed):
    with pytest.raises(SystemExit, match="nothing_here"):
        kaggle_pack.write_data(processed, processed / "extra", workers=1, sources=["nothing_here"])


def test_extra_clips_read_back_from_their_own_folder_after_joining(processed, tmp_path_factory):
    # What run.py does on Kaggle: both packs' shards by full path in one index,
    # read from a third folder.
    main_dir, extra_dir = processed / "kaggle" / "data", processed / "kaggle" / "extra"
    kaggle_pack.write_data(processed, main_dir, workers=1)
    kaggle_pack.write_data(processed, extra_dir, workers=1, sources=["small"])
    main = pd.read_parquet(main_dir / kaggle_pack.INDEX)
    main = main[main["source"] == "big"].assign(shard=lambda d: [str(main_dir / s) for s in d["shard"]])
    more = pd.read_parquet(extra_dir / kaggle_pack.EXTRA_INDEX)
    more = more.assign(shard=[str(extra_dir / s) for s in more["shard"]])
    joined = pd.concat([main, more], ignore_index=True)

    packed = ClipDataset(joined, tmp_path_factory.mktemp("elsewhere"))

    assert all(len(packed.read(i)) > 0 for i in range(len(joined)))


def test_a_rawboost_run_with_extra_data_attaches_it_and_asks_for_rawboost(tmp_path):
    out = tmp_path / "script"
    kaggle_pack.write_script(kaggle_pack.Path(kaggle_pack.__file__).parent, out, "someone", "xlsr2", 8, 8.0,
                             resume=False, noise=True, arch="ssl", extra=True, rawboost=True)
    script = (out / "run.py").read_text(encoding="utf-8")
    compile(script, "run.py", "exec")
    assert "NAME, EPOCHS, MAX_HOURS, RESUME, NOISE, EXTRA = 'xlsr2', 8, 8.0, False, True, True" in script
    assert repr(kaggle_pack.SSL_TRAIN_ARGS + ["--rawboost"]) in script
    meta = json.loads((out / "kernel-metadata.json").read_text())
    assert f"someone/{kaggle_pack.EXTRA_DATASET}" in meta["dataset_sources"]
