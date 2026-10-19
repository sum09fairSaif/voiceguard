import pytest
from cryptography.fernet import Fernet

import config
from identity_check import IdentityUnavailable
from voiceprints import build_voiceprint, has_voiceprint, load_voiceprint, save_voiceprint

USER_ID = "user-1"
VOICEPRINT = [0.123456, -0.5, 0.25]


def test_saved_voiceprint_comes_back(voiceprints):
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)

    assert load_voiceprint(voiceprints, USER_ID) == VOICEPRINT


def test_voiceprint_is_stored_encrypted(voiceprints):
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)

    stored = voiceprints.find_one({"_id": USER_ID})
    assert "0.123456" not in str(stored)
    assert stored["model"] == config.EMBEDDING_MODEL


def test_user_without_a_voiceprint_gets_none(voiceprints):
    assert load_voiceprint(voiceprints, USER_ID) is None


def test_saving_again_replaces_the_voiceprint(voiceprints):
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)
    save_voiceprint(voiceprints, USER_ID, [1.0, 2.0, 3.0])

    assert voiceprints.count_documents({}) == 1
    assert load_voiceprint(voiceprints, USER_ID) == [1.0, 2.0, 3.0]


def test_voiceprint_from_another_model_counts_as_not_enrolled(voiceprints, monkeypatch):
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "some/other-model")

    assert load_voiceprint(voiceprints, USER_ID) is None


def test_missing_key_is_reported_as_unavailable(voiceprints, monkeypatch):
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)
    monkeypatch.setattr(config, "VOICEPRINT_KEY", "")

    with pytest.raises(IdentityUnavailable):
        load_voiceprint(voiceprints, USER_ID)


def test_wrong_key_is_reported_as_unavailable(voiceprints, monkeypatch):
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)
    monkeypatch.setattr(config, "VOICEPRINT_KEY", Fernet.generate_key().decode())

    with pytest.raises(IdentityUnavailable):
        load_voiceprint(voiceprints, USER_ID)


def test_voiceprint_is_the_average_of_the_takes():
    # Each take is scaled to length 1 first, so a louder take doesn't count more.
    assert build_voiceprint([[3.0, 0.0], [0.0, 1.0]]) == pytest.approx([0.5, 0.5])


def test_voiceprint_needs_a_recording_with_voice_in_it():
    with pytest.raises(ValueError):
        build_voiceprint([])
    with pytest.raises(ValueError):
        build_voiceprint([[0.0, 0.0]])


def test_has_voiceprint_only_for_the_current_model(voiceprints, monkeypatch):
    assert has_voiceprint(voiceprints, USER_ID) is False
    save_voiceprint(voiceprints, USER_ID, VOICEPRINT)
    assert has_voiceprint(voiceprints, USER_ID) is True

    monkeypatch.setattr(config, "EMBEDDING_MODEL", "some/other-model")
    assert has_voiceprint(voiceprints, USER_ID) is False
