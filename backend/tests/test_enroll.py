import logging
import math
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

import config
from audio_upload import MAX_AUDIO_BYTES
from embedding import Embedding, get_embedder
from identity_check import IdentityUnavailable
from main import app
from passages import UNCHECKED_WORDS
from security import create_access_token
from transcription import AudioNotUnderstood, TranscriptionUnavailable, get_transcriber
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
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


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


class FakeTranscriber:
    # Stands in for Whisper. Unless the test sets `heard`, it hears the
    # newest sentence the user was given, read perfectly.
    def __init__(self, prompts):
        self.prompts = prompts
        self.heard = None
        self.error = None
        self.calls = []

    def __call__(self, audio, filename):
        self.calls.append((audio, filename))
        if self.error:
            raise self.error
        if self.heard is not None:
            return self.heard
        return newest_prompt(self.prompts)


@pytest.fixture(autouse=True)
def transcriber(enroll_prompts):
    fake = FakeTranscriber(enroll_prompts)
    app.dependency_overrides[get_transcriber] = lambda: fake
    return fake


def newest_prompt(prompts, user_id=USER_ID):
    newest = list(prompts.find({"user_id": user_id}).sort("created_at", -1).limit(1))
    return newest[0]["passage"] if newest else ""


def send(client, audio=RECORDING, content_type="audio/webm;codecs=opus", headers=None):
    # Like the screen: get the sentence to read, then send the recording.
    client.get(STATUS_URL, headers=signed_in() if headers is None else headers)
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
    assert response.json() == {"status": "enrolled", "samples_accepted": 3, "samples_required": 3, "prompt": None}
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


# --- Every word of the sentence, in order -------------------------------------


def read_with(client, enroll_prompts, transcriber, change):
    """Get a sentence, have the fake Whisper hear `change(words)` of it, and
    send the sample."""
    client.get(STATUS_URL, headers=signed_in())
    words = newest_prompt(enroll_prompts).rstrip(".").split()
    transcriber.heard = " ".join(change(words))
    return client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})


WRONG_WORDS_MESSAGE = "We didn't hear every word of the sentence, in order."


def test_the_whole_sentence_read_is_accepted(client, embedder, transcriber, enroll_prompts, enrollments):
    response = read_with(client, enroll_prompts, transcriber, lambda words: words)

    assert response.status_code == 200
    assert stored(enrollments) == 1


def test_capitals_and_punctuation_dont_matter(client, embedder, transcriber, enroll_prompts):
    response = read_with(client, enroll_prompts, transcriber, lambda words: [w.upper() + "," for w in words])

    assert response.status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        lambda words: words[:-1],  # last word dropped
        lambda words: words[1:],  # first word ("the") dropped
        lambda words: words[:4] + words[5:],  # a word in the middle dropped
        lambda words: [w for w in words if w != "the"],  # every "the" dropped
    ],
    ids=["last-word", "first-the", "middle-word", "every-the"],
)
def test_any_missing_word_is_rejected(client, embedder, transcriber, enroll_prompts, enrollments, change):
    response = read_with(client, enroll_prompts, transcriber, change)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(WRONG_WORDS_MESSAGE)
    assert stored(enrollments) == 0


def test_words_out_of_order_are_rejected(client, embedder, transcriber, enroll_prompts, enrollments):
    # "The sleepy tiger polished the rusty lantern ..." read with the two
    # key nouns swapped.
    def swap(words):
        words = list(words)
        words[2], words[6] = words[6], words[2]
        return words

    response = read_with(client, enroll_prompts, transcriber, swap)

    assert response.status_code == 422
    assert stored(enrollments) == 0


def test_the_sentence_backwards_is_rejected(client, embedder, transcriber, enroll_prompts):
    assert read_with(client, enroll_prompts, transcriber, lambda words: words[::-1]).status_code == 422


def test_a_stumble_or_two_is_allowed(client, embedder, transcriber, enroll_prompts):
    response = read_with(client, enroll_prompts, transcriber, lambda words: words[:3] + words[2:3] + ["um"] + words[3:])

    assert response.status_code == 200


def test_more_extra_words_than_allowed_are_rejected(client, embedder, transcriber, enroll_prompts):
    extra = ["and", "then", "something", "else"]

    assert read_with(client, enroll_prompts, transcriber, lambda words: words + extra).status_code == 422


def test_a_rejected_sentence_can_be_read_again(client, embedder, transcriber, enroll_prompts, enrollments):
    read_with(client, enroll_prompts, transcriber, lambda words: words[:-1])
    passage = newest_prompt(enroll_prompts)
    transcriber.heard = passage

    response = client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})

    assert response.status_code == 200
    assert stored(enrollments) == 1


def test_a_sentence_never_given_out_is_rejected(client, embedder, transcriber):
    transcriber.heard = "the happy painter carried the shiny ladder near the river"

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(WRONG_WORDS_MESSAGE)


def test_without_asking_for_a_sentence_no_sample_is_accepted(client, embedder, transcriber, enrollments):
    transcriber.heard = "the happy painter carried the shiny ladder near the river"

    response = client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})

    assert response.status_code == 422
    assert stored(enrollments) == 0


def test_one_sentence_counts_for_one_sample_only(client, embedder, transcriber, enroll_prompts, enrollments):
    # Otherwise one good recording could be sent three times.
    client.get(STATUS_URL, headers=signed_in())
    transcriber.heard = newest_prompt(enroll_prompts)
    upload = {"audio": ("s.webm", RECORDING, "audio/webm")}
    assert client.post(SAMPLES_URL, headers=signed_in(), files=upload).status_code == 200

    response = client.post(SAMPLES_URL, headers=signed_in(), files=upload)

    assert response.status_code == 422
    assert stored(enrollments) == 1


def test_an_earlier_sentence_still_counts_if_the_screen_asked_twice(client, embedder, transcriber, enroll_prompts):
    client.get(STATUS_URL, headers=signed_in())
    first = newest_prompt(enroll_prompts)
    client.get(STATUS_URL, headers=signed_in())
    transcriber.heard = first

    response = client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})

    assert response.status_code == 200


def test_only_the_newest_sentences_are_kept(client, enroll_prompts, monkeypatch):
    monkeypatch.setattr(config, "ENROLL_PROMPTS_KEPT", 3)
    for _ in range(6):
        client.get(STATUS_URL, headers=signed_in())

    assert enroll_prompts.count_documents({"user_id": USER_ID}) == 3


def test_an_expired_sentence_doesnt_count(client, embedder, transcriber, enroll_prompts):
    client.get(STATUS_URL, headers=signed_in())
    transcriber.heard = newest_prompt(enroll_prompts)
    enroll_prompts.update_many({}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}})

    response = client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})

    assert response.status_code == 422


def test_someone_elses_sentence_doesnt_count(client, embedder, transcriber, enroll_prompts):
    other = str(ObjectId())
    client.get(STATUS_URL, headers=signed_in(other))
    transcriber.heard = newest_prompt(enroll_prompts, other)

    response = client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})

    assert response.status_code == 422


def test_sentences_are_cleared_once_enrolled(client, embedder, enroll_prompts):
    for _ in range(3):
        send(client)

    assert enroll_prompts.count_documents({"user_id": USER_ID}) == 0


def test_recording_reaches_whisper_with_a_safe_filename(client, embedder, transcriber):
    send(client)

    assert transcriber.calls == [(RECORDING, "sample.webm")]


@pytest.mark.parametrize(
    "spoil",
    [
        lambda e: setattr(e, "speech_seconds", 0.4),
        lambda e: setattr(e, "clipped_share", 0.2),
        lambda e: setattr(e, "liveness", config.LIVENESS_THRESHOLD - 1.0),
    ],
    ids=["too-short", "too-loud", "not-live"],
)
def test_a_sample_already_turned_away_doesnt_pay_for_speech_to_text(client, embedder, transcriber, spoil):
    spoil(embedder)

    assert send(client).status_code == 422
    assert transcriber.calls == []


def test_an_inconsistent_sample_doesnt_pay_for_speech_to_text(client, embedder, transcriber):
    embedder.voices = [TAKES[0], OTHER_VOICE]
    send(client)

    assert send(client).status_code == 422
    assert len(transcriber.calls) == 1


def test_a_recording_whisper_cannot_read_asks_to_record_again(client, embedder, transcriber, enrollments):
    transcriber.error = AudioNotUnderstood("bad audio")

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"] == "We couldn't read that recording. Please record it again."
    assert stored(enrollments) == 0


def test_speech_to_text_outage_returns_503_and_keeps_nothing(client, embedder, transcriber, enrollments):
    transcriber.error = TranscriptionUnavailable("down")

    assert send(client).status_code == 503
    assert stored(enrollments) == 0


# --- Each sample close to every earlier one ----------------------------------


def at_angle(degrees):
    # A made-up voice pointing `degrees` away from the first take: the
    # similarity between two of them is the cosine of the angle between.
    radians = math.radians(degrees)
    return [math.cos(radians), math.sin(radians), 0.0]


def test_a_sample_close_to_the_average_but_far_from_one_take_is_rejected(
    client, embedder, enrollments, monkeypatch
):
    monkeypatch.setattr(config, "ENROLL_SAMPLES_REQUIRED", 4)
    # Takes at 0, 50 and 25 degrees average out at 25. A fourth at 60 is
    # 35 degrees from that average (similarity 0.82) but 60 from the first
    # take (0.50).
    embedder.voices = [at_angle(0), at_angle(50), at_angle(25), at_angle(60)]
    for _ in range(3):
        assert send(client).status_code == 200

    response = send(client)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("That recording doesn't sound like your earlier ones.")
    assert stored(enrollments) == 3


def test_a_sample_just_above_the_consistency_bar_is_accepted(client, embedder, monkeypatch):
    bar = config.ENROLL_CONSISTENCY_THRESHOLD
    embedder.voices = [at_angle(0), at_angle(math.degrees(math.acos(bar)) - 0.5)]
    send(client)

    assert send(client).status_code == 200


def test_a_sample_just_below_the_consistency_bar_is_rejected(client, embedder):
    bar = config.ENROLL_CONSISTENCY_THRESHOLD
    embedder.voices = [at_angle(0), at_angle(math.degrees(math.acos(bar)) + 0.5)]
    send(client)

    assert send(client).status_code == 422


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

    lines = [
        r.getMessage()
        for r in caplog.records
        if r.name == "voiceguard.enroll" and r.getMessage().startswith("enroll_sample")
    ]
    assert lines == [
        (
            f"enroll_sample user={USER_ID} outcome=accepted speech_seconds=2.00 clipped_share=0.0000 "
            f"liveness={config.LIVENESS_THRESHOLD + 1.0:.3f} similarity=- words=10/10 extra_words=0"
        ),
        (
            f"enroll_sample user={USER_ID} outcome=inconsistent speech_seconds=2.00 clipped_share=0.0000 "
            f"liveness={config.LIVENESS_THRESHOLD + 1.0:.3f} similarity=0.000 words=- extra_words=-"
        ),
    ]


def test_a_sample_with_missing_words_is_logged_without_the_words(client, embedder, transcriber, enroll_prompts, caplog):
    client.get(STATUS_URL, headers=signed_in())
    passage = newest_prompt(enroll_prompts)
    transcriber.heard = " ".join(passage.split()[:-2])

    with caplog.at_level(logging.INFO, logger="voiceguard.enroll"):
        client.post(SAMPLES_URL, headers=signed_in(), files={"audio": ("s.webm", RECORDING, "audio/webm")})

    lines = [r.getMessage() for r in caplog.records if r.name == "voiceguard.enroll"]
    [sample_line] = [line for line in lines if line.startswith("enroll_sample")]
    assert "outcome=wrong_words" in sample_line
    assert sample_line.endswith("words=8/10 extra_words=0")
    [paid_call] = [line for line in lines if line.startswith("transcription")]
    assert f"transcription user={USER_ID} attempt=enroll " in paid_call
    for line in lines:
        for word in passage.rstrip(".").split()[1:]:
            if word not in UNCHECKED_WORDS:
                assert f" {word} " not in f" {line} "
