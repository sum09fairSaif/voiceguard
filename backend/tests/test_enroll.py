import logging
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

import config
from audio_upload import MAX_AUDIO_BYTES
from embedding import Embedding, get_embedder
from identity_check import IdentityUnavailable
from main import app
from security import create_access_token
from transcription import AudioNotUnderstood
from voiceprints import load_voiceprint, save_voiceprint

STATUS_URL = "/api/enroll"
SAMPLES_URL = "/api/enroll/samples"
USER_ID = str(ObjectId())
RECORDING = b"pretend this is a few seconds of speech"

# Made-up voices. The user's takes all point roughly the same way; the
# other voice is at right angles to them (similarity 0).
TAKES = [[0.6, 0.8, 0.0], [0.62, 0.78, 0.05], [0.58, 0.81, -0.03]]
OTHER_VOICE = [0.0, 0.0, 1.0]


def signed_in(user_id=USER_ID):
    # The signup session: the only one allowed to enroll (see the
    # enrollment window tests at the end).
    return {"Authorization": f"Bearer {create_access_token(user_id, source='signup')}"}


@pytest.fixture(autouse=True)
def account(users):
    # Enrollment checks when the account was made, so it has to exist.
    users.insert_one({"_id": ObjectId(USER_ID), "full_name": "Sam Doe", "email": "sam@example.com",
                      "created_at": datetime.now(UTC)})


class FakeEmbedder:
    # Stands in for the model service: hands out the next voice in `voices`
    # with the quality the test sets, and remembers what it was sent.
    def __init__(self):
        self.voices = list(TAKES)
        self.speech_seconds = 2.0
        self.clipped_share = 0.0
        self.liveness = config.LIVENESS_THRESHOLD + 1.0
        self.liveness_model = "aasist-test"
        self.error = None
        self.calls = []

    def __call__(self, audio, filename):
        self.calls.append((audio, filename))
        if self.error:
            raise self.error
        return Embedding(
            vector=self.voices.pop(0),
            speech_seconds=self.speech_seconds,
            clipped_share=self.clipped_share,
            liveness_model=self.liveness_model,
            liveness=self.liveness,
        )


@pytest.fixture
def embedder():
    fake = FakeEmbedder()
    app.dependency_overrides[get_embedder] = lambda: fake
    return fake


def send(client, audio=RECORDING, content_type="audio/webm;codecs=opus", headers=None):
    return client.post(
        SAMPLES_URL,
        headers=signed_in() if headers is None else headers,
        files={"audio": ("../../etc/sample.webm", audio, content_type)},
    )


def stored(enrollments):
    record = enrollments.find_one({"_id": USER_ID})
    return len(record["samples"]) if record else 0


# --- The happy path -------------------------------------------------------------


def test_new_user_has_not_started(client):
    body = client.get(STATUS_URL, headers=signed_in()).json()

    assert body["status"] == "not_started"
    assert body["samples_accepted"] == 0
    assert body["samples_required"] == 3
    assert body["prompt"].startswith("The ") and body["prompt"].endswith(".")
    assert len(body["prompt"].split()) == 10


def test_each_good_sample_counts_towards_enrollment(client, embedder, voiceprints):
    response = send(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["samples_accepted"] == 1
    assert body["prompt"]
    assert load_voiceprint(voiceprints, USER_ID) is None


def test_third_good_sample_creates_the_voiceprint(client, embedder, voiceprints, enrollments):
    for _ in range(2):
        send(client)

    response = send(client)

    assert response.status_code == 200
    assert response.json() == {
        "status": "enrolled",
        "samples_accepted": 3,
        "samples_required": 3,
        "prompt": None,
        # Nothing more to record once enrolled.
        "can_enroll": False,
    }
    voiceprint = load_voiceprint(voiceprints, USER_ID)
    assert voiceprint is not None
    assert len(voiceprint) == 3
    # The samples are gone once the voiceprint is made.
    assert enrollments.count_documents({}) == 0
    assert client.get(STATUS_URL, headers=signed_in()).json()["status"] == "enrolled"


def test_recording_reaches_the_model_service_with_a_safe_filename(client, embedder):
    send(client)

    # The format comes from the content type; the uploaded filename is ignored.
    assert embedder.calls == [(RECORDING, "sample.webm")]


def test_samples_are_stored_encrypted(client, embedder, enrollments):
    send(client)

    record = enrollments.find_one({"_id": USER_ID})
    assert "0.6" not in str(record["samples"])
    assert "0.8" not in str(record["samples"])


def test_starting_over_throws_away_the_samples(client, embedder, enrollments):
    send(client)
    send(client)

    response = client.delete(SAMPLES_URL, headers=signed_in())

    assert response.status_code == 200
    assert response.json()["status"] == "not_started"
    assert enrollments.count_documents({}) == 0


def test_unfinished_samples_expire(client, embedder, enrollments):
    send(client)
    enrollments.update_one(
        {"_id": USER_ID}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )

    assert client.get(STATUS_URL, headers=signed_in()).json()["status"] == "not_started"
    # A new sample starts afresh instead of joining the expired ones.
    assert send(client).json()["samples_accepted"] == 1


def test_samples_from_another_model_are_not_mixed_in(client, embedder, enrollments, monkeypatch):
    send(client)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "some/other-model")

    assert send(client).json()["samples_accepted"] == 1


# --- Poor samples are turned away with a way to fix them --------------------


def test_too_short_or_quiet_sample_is_rejected(client, embedder, enrollments):
    embedder.speech_seconds = 0.4

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("That recording was too short or too quiet.")
    assert stored(enrollments) == 0


def test_distorted_sample_is_rejected(client, embedder, enrollments):
    embedder.clipped_share = 0.2

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("That recording was too loud")
    assert stored(enrollments) == 0


def test_recording_or_clone_is_rejected(client, embedder, enrollments):
    embedder.liveness = config.LIVENESS_THRESHOLD - 1.0

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("That recording didn't sound like a live voice.")
    assert stored(enrollments) == 0


def test_score_exactly_at_the_liveness_threshold_is_accepted(client, embedder, enrollments):
    embedder.liveness = config.LIVENESS_THRESHOLD

    assert send(client).status_code == 200
    assert stored(enrollments) == 1


def test_sample_with_nothing_to_judge_fails_liveness(client, embedder, enrollments):
    embedder.liveness = None

    assert send(client).status_code == 422
    assert stored(enrollments) == 0


def test_a_clone_after_two_good_samples_doesnt_finish_the_voiceprint(client, embedder, voiceprints, enrollments):
    send(client)
    send(client)
    embedder.liveness = config.LIVENESS_THRESHOLD - 1.0

    assert send(client).status_code == 422
    assert stored(enrollments) == 2
    assert voiceprints.find_one({"_id": USER_ID}) is None


def test_model_service_without_liveness_returns_503(client, embedder, enrollments):
    embedder.liveness_model = None

    assert send(client).status_code == 503
    assert stored(enrollments) == 0


def test_sample_unlike_the_earlier_ones_is_rejected(client, embedder, enrollments):
    embedder.voices = [TAKES[0], OTHER_VOICE, TAKES[1]]
    send(client)

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("That recording doesn't sound like your earlier ones.")
    assert stored(enrollments) == 1
    # Recording again works.
    assert send(client).json()["samples_accepted"] == 2


def test_recording_the_model_service_cannot_read_asks_to_record_again(client, embedder):
    embedder.error = AudioNotUnderstood("The model service couldn't read the recording.")

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"] == "We couldn't read that recording. Please record it again."


def test_non_audio_upload_is_refused(client, embedder):
    assert send(client, content_type="text/plain").status_code == 415
    assert embedder.calls == []


def test_oversized_recording_is_refused(client, embedder):
    assert send(client, audio=b"x" * (MAX_AUDIO_BYTES + 1)).status_code == 413
    assert embedder.calls == []


def test_empty_recording_is_refused(client, embedder):
    assert send(client, audio=b"").status_code == 400
    assert embedder.calls == []


# --- Who can enroll -----------------------------------------------------------


def test_no_token_is_refused(client, embedder):
    assert send(client, headers={}).status_code == 401
    assert client.get(STATUS_URL).status_code == 401
    assert client.delete(SAMPLES_URL).status_code == 401
    assert embedder.calls == []


def test_an_enrolled_voice_cannot_be_replaced(client, embedder, voiceprints):
    # Otherwise someone who only knows the password could swap in their own voice.
    save_voiceprint(voiceprints, USER_ID, TAKES[0])

    response = send(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Your voice is already enrolled."
    assert embedder.calls == []
    assert load_voiceprint(voiceprints, USER_ID) == TAKES[0]


def test_starting_over_leaves_a_finished_voiceprint_alone(client, voiceprints):
    save_voiceprint(voiceprints, USER_ID, TAKES[0])

    assert client.delete(SAMPLES_URL, headers=signed_in()).json()["status"] == "enrolled"
    assert load_voiceprint(voiceprints, USER_ID) == TAKES[0]


def test_one_users_samples_dont_count_for_another(client, embedder):
    send(client)

    body = client.get(STATUS_URL, headers=signed_in(str(ObjectId()))).json()

    assert body["status"] == "not_started"


def test_too_many_samples_are_refused(client, embedder, monkeypatch):
    monkeypatch.setattr(config, "ENROLL_RATE_LIMIT", 2)
    embedder.speech_seconds = 0.1  # rejected samples count too
    for _ in range(2):
        send(client)

    response = send(client)

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert len(embedder.calls) == 2


# --- Outages ------------------------------------------------------------------


def test_unconfigured_model_service_returns_503(client):
    app.dependency_overrides[get_embedder] = lambda: None

    response = send(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice checks are temporarily unavailable. Please try again shortly."


def test_missing_voiceprint_key_returns_503_before_calling_the_model_service(client, embedder, monkeypatch):
    monkeypatch.setattr(config, "VOICEPRINT_KEY", "")

    assert send(client).status_code == 503
    assert embedder.calls == []


def test_model_service_outage_returns_503(client, embedder):
    embedder.error = IdentityUnavailable("The model service can't be reached.")

    assert send(client).status_code == 503


def test_model_service_outage_logs_which_part_failed_and_why(client, embedder, caplog):
    embedder.error = IdentityUnavailable("The model service can't be reached: ConnectError status=-.")

    with caplog.at_level(logging.WARNING, logger="voiceguard"):
        response = send(client)

    assert "ConnectError" not in response.text
    [line] = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == "voiceguard"]
    assert "path=/api/enroll/samples part=voice-model" in line
    assert "ConnectError status=-" in line


def test_model_service_too_old_to_measure_quality_returns_503(client, embedder, enrollments):
    embedder.speech_seconds = None

    assert send(client).status_code == 503
    assert stored(enrollments) == 0


def test_embedding_from_a_different_model_returns_503(client, embedder):
    embedder.voices = [TAKES[0], [0.1, 0.2]]
    send(client)

    assert send(client).status_code == 503


# --- Logging -------------------------------------------------------------------


def test_each_sample_is_logged_without_the_voice(client, embedder, caplog):
    embedder.voices = [TAKES[0], OTHER_VOICE]

    with caplog.at_level(logging.INFO, logger="voiceguard.enroll"):
        send(client)
        send(client)

    lines = [r.getMessage() for r in caplog.records if r.name == "voiceguard.enroll"]
    assert lines == [
        (
            f"enroll_sample user={USER_ID} outcome=accepted speech_seconds=2.00 clipped_share=0.0000 "
            f"liveness={config.LIVENESS_THRESHOLD + 1.0:.3f} similarity=-"
        ),
        (
            f"enroll_sample user={USER_ID} outcome=inconsistent speech_seconds=2.00 clipped_share=0.0000 "
            f"liveness={config.LIVENESS_THRESHOLD + 1.0:.3f} similarity=0.000"
        ),
    ]


# --- Only the signup session may enroll (#155) ---------------------------------

SOON = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)


def from_login(user_id=USER_ID):
    return {"Authorization": f"Bearer {create_access_token(user_id, source='login')}"}


@pytest.fixture
def no_grace(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", None)


def made(users, minutes_ago):
    users.update_one(
        {"_id": ObjectId(USER_ID)}, {"$set": {"created_at": datetime.now(UTC) - timedelta(minutes=minutes_ago)}}
    )


def test_the_signup_session_may_enroll(client, embedder, no_grace):
    assert client.get(STATUS_URL, headers=signed_in()).json()["can_enroll"] is True
    assert send(client).status_code == 200


def test_the_signup_session_closes_after_the_window(client, users, embedder, no_grace):
    made(users, config.ENROLL_WINDOW_MINUTES + 1)

    response = send(client)

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Voice ID can only be set up right after creating your account.")
    assert client.get(STATUS_URL, headers=signed_in()).json()["can_enroll"] is False
    assert embedder.calls == []


def test_a_password_sign_in_may_not_enroll(client, embedder, no_grace):
    # Someone who only knows the password can't attach their own voice.
    response = send(client, headers=from_login())

    assert response.status_code == 403
    assert client.get(STATUS_URL, headers=from_login()).json()["can_enroll"] is False
    assert embedder.calls == []


def test_a_token_from_before_these_changes_is_refused(client, embedder, no_grace):
    import jwt

    now = datetime.now(UTC)
    old = jwt.encode(
        {"sub": USER_ID, "iat": now, "exp": now + timedelta(minutes=5)}, config.JWT_SECRET, algorithm="HS256"
    )

    # No session, issuer or audience: refused outright (sign in again).
    assert send(client, headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_the_grace_period_lets_an_older_account_enroll_after_signing_in(client, users, embedder, monkeypatch):
    made(users, 60 * 24 * 10)  # ten days old, never enrolled
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", datetime.now(UTC) + timedelta(hours=1))

    assert client.get(STATUS_URL, headers=from_login()).json()["can_enroll"] is True
    assert send(client, headers=from_login()).status_code == 200


def test_the_grace_period_ends_at_the_cut_off(client, users, embedder, monkeypatch):
    made(users, 60 * 24 * 10)
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", datetime.now(UTC) - timedelta(minutes=1))

    assert send(client, headers=from_login()).status_code == 403


def test_an_account_made_after_the_cut_off_gets_no_grace(client, users, embedder, monkeypatch):
    # Created after the cut-off, an hour ago: only its own signup session counted.
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", datetime.now(UTC) - timedelta(hours=2))
    made(users, 60)

    assert send(client, headers=from_login()).status_code == 403


def test_an_enrolled_account_still_gets_409_not_403(client, voiceprints, embedder, no_grace):
    save_voiceprint(voiceprints, USER_ID, [0.6, 0.8, 0.0])

    assert send(client, headers=from_login()).status_code == 409


def test_a_missing_account_may_not_enroll(client, users, embedder):
    users.delete_many({})

    assert send(client).status_code == 403


def test_refused_requests_dont_use_up_the_owners_allowance(client, embedder, monkeypatch, no_grace):
    # Someone with only the password keeps trying; the owner's signup session
    # can still enroll.
    monkeypatch.setattr(config, "ENROLL_RATE_LIMIT", 1)
    for _ in range(3):
        assert send(client, headers=from_login()).status_code == 403

    assert send(client).status_code == 200


def test_new_signups_are_flagged_and_get_no_grace(client, users, embedder, monkeypatch):
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", datetime.now(UTC) + timedelta(hours=6))
    client.post(
        "/api/auth/signup",
        json={"full_name": "New Person", "email": "new@example.com", "password": "correct-horse-battery"},
    )
    new_user = users.find_one({"email": "new@example.com"})
    assert new_user["signup_session_enrollment"] is True

    response = send(client, headers=from_login(str(new_user["_id"])))

    assert response.status_code == 403


# --- Security events (#167) ----------------------------------------------------


def recorded(audit_events):
    return [(e["event"], e["reason"]) for e in audit_events.find({}, {"_id": 0})]


def test_enrollment_is_recorded(client, embedder, audit_events):
    for _ in range(config.ENROLL_SAMPLES_REQUIRED):
        send(client)

    assert recorded(audit_events) == [("enroll_sample_accepted", None)] * config.ENROLL_SAMPLES_REQUIRED + [
        ("enrolled", None)
    ]


def test_a_refused_sample_records_why(client, embedder, audit_events):
    embedder.speech_seconds = 0.1
    send(client)

    ((event, reason),) = recorded(audit_events)
    assert event == "enroll_sample_refused"
    assert reason


def test_enrolling_outside_the_signup_session_is_recorded(client, embedder, audit_events, no_grace):
    send(client, headers=from_login())

    assert recorded(audit_events) == [("enroll_sample_refused", "not_signup_session")]
