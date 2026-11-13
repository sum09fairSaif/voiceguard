import logging
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

import config
from audio_upload import MAX_AUDIO_BYTES
from challenges import create_challenge
from db import get_challenges_collection
from embedding import Embedding, get_embedder
from identity_check import IdentityUnavailable
from main import app
from security import create_access_token
from transcription import AudioNotUnderstood, TranscriptionUnavailable, get_openai_client, get_transcriber
from voiceprints import save_voiceprint

VERIFY_URL = "/api/verify"
USER_ID = str(ObjectId())
RECORDING = b"pretend this is a few seconds of speech"


def signed_in(user_id=USER_ID):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


class FakeTranscriber:
    # Stands in for Whisper: "hears" whatever the test says and remembers
    # what it was sent.
    def __init__(self, heard="", error=None):
        self.heard = heard
        self.error = error
        self.calls = []

    def __call__(self, audio, filename):
        self.calls.append((audio, filename))
        if self.error:
            raise self.error
        return self.heard


@pytest.fixture
def transcriber():
    fake = FakeTranscriber()
    app.dependency_overrides[get_transcriber] = lambda: fake
    return fake


# Liveness scores either side of the threshold, whatever it's set to.
LIVE = config.LIVENESS_THRESHOLD + 1.0
SPOOFED = config.LIVENESS_THRESHOLD - 1.0


class FakeEmbedder:
    # Stands in for the model service: returns whatever voice and liveness
    # score the test sets and remembers what it was sent.
    def __init__(self, voice=None, error=None):
        self.voice = voice
        self.liveness = LIVE
        self.liveness_model = "aasist-test"
        self.error = error
        self.calls = []

    def __call__(self, audio, filename):
        self.calls.append((audio, filename))
        if self.error:
            raise self.error
        return Embedding(
            vector=self.voice,
            speech_seconds=2.0,
            clipped_share=0.0,
            liveness_model=self.liveness_model,
            liveness=self.liveness,
        )


# Two made-up voices at right angles to each other: similarity 0.
USERS_VOICE = [0.6, 0.8, 0.0]
OTHER_VOICE = [0.0, 0.0, 1.0]


@pytest.fixture
def embedder():
    fake = FakeEmbedder(voice=USERS_VOICE)
    app.dependency_overrides[get_embedder] = lambda: fake
    return fake


@pytest.fixture
def enrolled(voiceprints):
    save_voiceprint(voiceprints, USER_ID, USERS_VOICE)


@pytest.fixture
def attempt(challenges):
    challenge = create_challenge(challenges, USER_ID)
    return {"id": str(challenge["_id"]), "passage": challenge["passage"]}


def submit(client, attempt_id, audio=RECORDING, content_type="audio/webm;codecs=opus", headers=None):
    return client.post(
        VERIFY_URL,
        headers=signed_in() if headers is None else headers,
        files={"audio": ("../../etc/recording.webm", audio, content_type)},
        data={"attempt_id": attempt_id},
    )


def is_unused(challenges, attempt_id):
    return challenges.find_one({"_id": ObjectId(attempt_id)})["used"] is False


# --- The voice check itself -------------------------------------------------


def test_reading_the_passage_without_a_voiceprint_is_not_approved(client, challenges, transcriber, attempt):
    # Speech-to-text may change capitals and punctuation; that still counts.
    transcriber.heard = attempt["passage"].upper().rstrip(".") + "!"
    response = submit(client, attempt["id"])

    assert response.status_code == 200
    assert response.json() == {
        "decision": "incomplete",
        "reason": "The passage was read correctly, but this account has no voiceprint yet.",
        "content": {"passed": True, "score": 1.0, "matched": 6, "total": 6},
        "identity": "not_enrolled",
        "liveness": "not_checked",
    }
    assert not is_unused(challenges, attempt["id"])


def test_wrong_words_are_rejected(client, transcriber, attempt):
    transcriber.heard = "the quick brown fox jumps over"
    response = submit(client, attempt["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["reason"] == "The words didn't match the passage."
    assert body["content"]["passed"] is False


def test_recording_reaches_whisper_with_a_safe_filename(client, transcriber, attempt):
    submit(client, attempt["id"])

    # The format comes from the content type; the uploaded filename is ignored.
    assert transcriber.calls == [(RECORDING, "attempt.webm")]


@pytest.mark.parametrize(
    "content_type, filename",
    [("audio/mp4", "attempt.mp4"), ("audio/ogg", "attempt.ogg"), ("audio/wav", "attempt.wav")],
)
def test_other_browser_formats_are_accepted(client, transcriber, attempt, content_type, filename):
    response = submit(client, attempt["id"], content_type=content_type)

    assert response.status_code == 200
    assert transcriber.calls[0][1] == filename


# --- Replay protection: each passage works once, for its owner, in time -----


def test_same_passage_cannot_be_checked_twice(client, transcriber, attempt):
    transcriber.heard = attempt["passage"]
    assert submit(client, attempt["id"]).status_code == 200

    response = submit(client, attempt["id"])

    assert response.status_code == 400
    assert response.json()["detail"] == "This passage has expired or was already used. Please get a new one."


def test_expired_passage_is_refused(client, challenges, transcriber, attempt):
    challenges.update_one(
        {"_id": ObjectId(attempt["id"])},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
    )

    assert submit(client, attempt["id"]).status_code == 400
    assert transcriber.calls == []


def test_someone_elses_passage_is_refused(client, challenges, transcriber, attempt):
    response = submit(client, attempt["id"], headers=signed_in(str(ObjectId())))

    assert response.status_code == 400
    assert is_unused(challenges, attempt["id"])


@pytest.mark.parametrize("attempt_id", ["not-an-id", str(ObjectId())], ids=["malformed", "unknown"])
def test_unknown_attempt_is_refused(client, transcriber, attempt_id):
    assert submit(client, attempt_id).status_code == 400


# --- Bad requests are turned away without using up the passage -------------


def test_no_token_is_refused(client, challenges, transcriber, attempt):
    response = submit(client, attempt["id"], headers={})

    assert response.status_code == 401
    assert is_unused(challenges, attempt["id"])


def test_non_audio_upload_is_refused(client, challenges, transcriber, attempt):
    response = submit(client, attempt["id"], content_type="text/plain")

    assert response.status_code == 415
    assert is_unused(challenges, attempt["id"])


def test_oversized_recording_is_refused(client, challenges, transcriber, attempt):
    response = submit(client, attempt["id"], audio=b"x" * (MAX_AUDIO_BYTES + 1))

    assert response.status_code == 413
    assert is_unused(challenges, attempt["id"])
    assert transcriber.calls == []


def test_empty_recording_is_refused(client, challenges, transcriber, attempt):
    response = submit(client, attempt["id"], audio=b"")

    assert response.status_code == 400
    assert is_unused(challenges, attempt["id"])


def test_missing_attempt_id_is_refused(client, transcriber):
    response = client.post(
        VERIFY_URL,
        headers=signed_in(),
        files={"audio": ("recording.webm", RECORDING, "audio/webm")},
    )

    assert response.status_code == 422


# --- Outages ----------------------------------------------------------------


def test_missing_openai_key_returns_503_and_keeps_the_passage(client, challenges, attempt, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    get_openai_client.cache_clear()
    response = submit(client, attempt["id"])
    get_openai_client.cache_clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice checks are temporarily unavailable. Please try again shortly."
    assert is_unused(challenges, attempt["id"])


def test_transcription_outage_returns_503(client, transcriber, attempt):
    transcriber.error = TranscriptionUnavailable("Speech-to-text request failed.")

    response = submit(client, attempt["id"])

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice checks are temporarily unavailable. Please try again shortly."


def test_unreadable_recording_asks_for_a_new_passage(client, transcriber, attempt):
    transcriber.error = AudioNotUnderstood("Speech-to-text couldn't read the recording.")

    response = submit(client, attempt["id"])

    assert response.status_code == 422
    assert response.json()["detail"] == "We couldn't process that recording. Please get a new passage and record again."


class UnreachableDatabase:
    def find_one_and_update(self, query, update):
        raise ServerSelectionTimeoutError("database unreachable")


def test_database_outage_returns_503(client, transcriber):
    app.dependency_overrides[get_challenges_collection] = lambda: UnreachableDatabase()

    assert submit(client, str(ObjectId())).status_code == 503

# --- Rate limit and spend log -------------------------------------------------


def test_too_many_checks_are_refused_without_using_the_passage(client, challenges, transcriber, monkeypatch):
    monkeypatch.setattr(config, "VERIFY_RATE_LIMIT", 2)
    for _ in range(2):
        submit(client, str(create_challenge(challenges, USER_ID)["_id"]))
    attempt_id = str(create_challenge(challenges, USER_ID)["_id"])

    response = submit(client, attempt_id)

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert len(transcriber.calls) == 2
    assert is_unused(challenges, attempt_id)


def test_each_transcription_is_logged_without_the_words(client, transcriber, attempt, caplog):
    transcriber.heard = attempt["passage"]

    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"])

    [line] = [r.getMessage() for r in caplog.records if r.name == "voiceguard.verify"]
    assert line.startswith(f"transcription user={USER_ID} attempt={attempt['id']} ")
    assert f"bytes={len(RECORDING)}" in line
    assert "format=webm" in line
    assert "outcome=ok" in line
    for word in attempt["passage"].split():
        assert word not in line


@pytest.mark.parametrize(
    "error, outcome",
    [
        (AudioNotUnderstood("bad audio"), "unreadable"),
        (TranscriptionUnavailable("down"), "unavailable"),
    ],
    ids=["unreadable", "unavailable"],
)
def test_failed_transcription_is_logged_too(client, transcriber, attempt, caplog, error, outcome):
    transcriber.error = error

    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"])

    [line] = [r.getMessage() for r in caplog.records if r.name == "voiceguard.verify"]
    assert f"outcome={outcome}" in line


def test_failed_transcription_logs_what_openai_answered(client, transcriber, attempt, caplog):
    transcriber.error = TranscriptionUnavailable("down", "RateLimitError status=429 code=insufficient_quota")

    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"])

    [line] = [r.getMessage() for r in caplog.records if r.name == "voiceguard.verify"]
    assert line.endswith("error=RateLimitError status=429 code=insufficient_quota")


def test_speech_to_text_outage_logs_one_warning_without_private_data(client, transcriber, attempt, caplog):
    transcriber.error = TranscriptionUnavailable("Speech-to-text request failed: RateLimitError status=429.")

    with caplog.at_level(logging.WARNING, logger="voiceguard"):
        response = submit(client, attempt["id"])

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]
    [line] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == "voiceguard"]
    assert "path=/api/verify part=speech-to-text" in line
    assert "RateLimitError status=429" in line
    assert "RateLimitError" not in response.text
    for word in attempt["passage"].split():
        assert word not in line
    assert RECORDING.decode() not in caplog.text


def test_missing_openai_key_logs_a_clear_warning(client, attempt, caplog, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    get_openai_client.cache_clear()

    with caplog.at_level(logging.WARNING, logger="voiceguard"):
        response = submit(client, attempt["id"])
    get_openai_client.cache_clear()

    assert response.status_code == 503
    assert "part=speech-to-text reason=OPENAI_API_KEY is not set." in caplog.text


def test_refused_requests_are_not_logged_as_transcriptions(client, transcriber, attempt, caplog):
    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"], content_type="text/plain")

    assert not [r for r in caplog.records if r.name == "voiceguard.verify"]


# --- Identity check ------------------------------------------------------------


def test_enrolled_user_reading_live_in_their_own_voice_is_approved(client, transcriber, embedder, enrolled, attempt):
    transcriber.heard = attempt["passage"]
    response = submit(client, attempt["id"])

    assert response.status_code == 200
    assert response.json() == {
        "decision": "approved",
        "reason": "The passage, the voice and liveness all checked out.",
        "content": {"passed": True, "score": 1.0, "matched": 6, "total": 6},
        "identity": "passed",
        "liveness": "passed",
    }
    assert embedder.calls == [(RECORDING, "attempt.webm")]


def test_different_speaker_is_rejected(client, transcriber, embedder, enrolled, attempt):
    transcriber.heard = attempt["passage"]
    embedder.voice = OTHER_VOICE
    response = submit(client, attempt["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["reason"] == "The voice didn't match this account."
    assert body["identity"] == "failed"


def test_identity_and_liveness_scores_are_not_sent_back(client, transcriber, embedder, enrolled, attempt):
    # A score would let someone tune a voice clone until it gets through.
    transcriber.heard = attempt["passage"]
    body = submit(client, attempt["id"]).json()

    assert body["identity"] == "passed"
    assert body["liveness"] == "passed"
    assert set(body) == {"decision", "reason", "content", "identity", "liveness"}


def test_identity_score_is_logged_for_tuning(client, transcriber, embedder, enrolled, attempt, caplog):
    embedder.voice = [0.6, 0.0, 0.8]  # similarity 0.36 with USERS_VOICE: below the threshold

    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"])

    lines = [r.getMessage() for r in caplog.records if r.message.startswith("identity ")]
    assert lines == [f"identity user={USER_ID} attempt={attempt['id']} score=0.360 passed=False"]


def test_user_without_a_voiceprint_is_not_sent_to_the_model_service(client, transcriber, embedder, attempt):
    body = submit(client, attempt["id"]).json()

    assert body["identity"] == "not_enrolled"
    assert body["liveness"] == "not_checked"
    assert embedder.calls == []


def test_unconfigured_model_service_returns_503_and_keeps_the_passage(
    client, challenges, transcriber, enrolled, attempt
):
    app.dependency_overrides[get_embedder] = lambda: None
    response = submit(client, attempt["id"])

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice checks are temporarily unavailable. Please try again shortly."
    assert is_unused(challenges, attempt["id"])
    assert transcriber.calls == []


def test_missing_voiceprint_key_returns_503_and_keeps_the_passage(
    client, challenges, transcriber, embedder, enrolled, attempt, monkeypatch
):
    monkeypatch.setattr(config, "VOICEPRINT_KEY", "")
    response = submit(client, attempt["id"])

    assert response.status_code == 503
    assert is_unused(challenges, attempt["id"])


def test_model_service_outage_returns_503(client, transcriber, embedder, enrolled, attempt):
    embedder.error = IdentityUnavailable("The model service can't be reached.")

    response = submit(client, attempt["id"])

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice checks are temporarily unavailable. Please try again shortly."


def test_embedding_from_a_different_model_returns_503(client, transcriber, embedder, enrolled, attempt):
    embedder.voice = [0.1, 0.2]  # not the voiceprint's size

    assert submit(client, attempt["id"]).status_code == 503


def test_recording_the_model_service_cannot_read_asks_for_a_new_passage(
    client, transcriber, embedder, enrolled, attempt
):
    embedder.error = AudioNotUnderstood("The model service couldn't read the recording.")

    response = submit(client, attempt["id"])

    assert response.status_code == 422
    assert response.json()["detail"] == "We couldn't process that recording. Please get a new passage and record again."


# --- Liveness check ------------------------------------------------------------


def test_replay_or_clone_of_the_users_own_voice_is_rejected(client, transcriber, embedder, enrolled, attempt):
    # The veto: the voice matches, but it isn't a live person.
    transcriber.heard = attempt["passage"]
    embedder.liveness = SPOOFED

    body = submit(client, attempt["id"]).json()

    assert body["decision"] == "rejected"
    assert body["reason"] == "The recording didn't sound like a live voice."
    assert body["identity"] == "passed"
    assert body["liveness"] == "failed"


def test_liveness_rejects_even_when_the_voice_is_also_wrong(client, transcriber, embedder, enrolled, attempt):
    transcriber.heard = attempt["passage"]
    embedder.voice = OTHER_VOICE
    embedder.liveness = SPOOFED

    body = submit(client, attempt["id"]).json()

    assert body["decision"] == "rejected"
    assert body["identity"] == "failed"
    assert body["liveness"] == "failed"


def test_score_exactly_at_the_threshold_passes(client, transcriber, embedder, enrolled, attempt):
    transcriber.heard = attempt["passage"]
    embedder.liveness = config.LIVENESS_THRESHOLD

    assert submit(client, attempt["id"]).json()["liveness"] == "passed"


def test_recording_with_nothing_to_judge_fails_liveness(client, transcriber, embedder, enrolled, attempt):
    # A check that couldn't run must not let the attempt through.
    transcriber.heard = attempt["passage"]
    embedder.liveness = None

    body = submit(client, attempt["id"]).json()

    assert body["decision"] == "rejected"
    assert body["liveness"] == "failed"


def test_model_service_without_liveness_returns_503(client, transcriber, embedder, enrolled, attempt):
    # An older model service sends no liveness score at all: that's a
    # server problem, not the user's.
    embedder.liveness_model = None
    embedder.liveness = None

    response = submit(client, attempt["id"])

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice checks are temporarily unavailable. Please try again shortly."


def test_liveness_score_is_logged_for_tuning(client, transcriber, embedder, enrolled, attempt, caplog, monkeypatch):
    monkeypatch.setattr(config, "LIVENESS_THRESHOLD", 0.5)
    embedder.liveness = 0.25

    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"])

    lines = [r.getMessage() for r in caplog.records if r.message.startswith("liveness ")]
    assert lines == [f"liveness user={USER_ID} attempt={attempt['id']} model=aasist-test score=0.250 passed=False"]


def test_missing_liveness_score_is_logged_as_a_dash(client, transcriber, embedder, enrolled, attempt, caplog):
    embedder.liveness = None

    with caplog.at_level(logging.INFO, logger="voiceguard.verify"):
        submit(client, attempt["id"])

    [line] = [r.getMessage() for r in caplog.records if r.message.startswith("liveness ")]
    assert "score=- passed=False" in line
