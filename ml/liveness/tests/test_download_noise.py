"""download.rirs_noises unpacks into a staging folder first, so an
interrupted unpack never looks finished."""

import zipfile

import download


def make_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("RIRS_NOISES/pointsource_noises/noise-1.wav", b"x")
        z.writestr("RIRS_NOISES/simulated_rirs/smallroom/Room001-00001.wav", b"x")


def test_the_unpacked_folder_appears_only_when_complete(tmp_path):
    make_zip(tmp_path / "rirs_noises.zip")

    download.rirs_noises(tmp_path)

    assert (tmp_path / "RIRS_NOISES" / "pointsource_noises" / "noise-1.wav").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["RIRS_NOISES"]


def test_an_earlier_interrupted_unpack_is_thrown_away(tmp_path):
    (tmp_path / "RIRS_NOISES.unpacking" / "RIRS_NOISES").mkdir(parents=True)
    (tmp_path / "RIRS_NOISES.unpacking" / "RIRS_NOISES" / "half.wav").write_bytes(b"x")
    make_zip(tmp_path / "rirs_noises.zip")

    download.rirs_noises(tmp_path)

    assert not (tmp_path / "RIRS_NOISES" / "half.wav").exists()
    assert not (tmp_path / "RIRS_NOISES.unpacking").exists()


def test_an_interrupted_unpack_doesnt_count_as_unpacked(tmp_path, capsys):
    # Only the staging folder exists, as after an interruption: not "already unpacked".
    (tmp_path / "RIRS_NOISES.unpacking").mkdir()
    make_zip(tmp_path / "rirs_noises.zip")

    download.rirs_noises(tmp_path)

    assert "already unpacked" not in capsys.readouterr().out
    assert (tmp_path / "RIRS_NOISES").is_dir()
