"""GET /api/me: the account summary, only for a voice-verified session."""

from datetime import UTC, datetime

from bson import ObjectId

from security import create_access_token, create_verified_token
from voiceprints import save_voiceprint

ME_URL = "/api/me"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_account(users, **extra):
    user_id = ObjectId()
    users.insert_one(
        {
            "_id": user_id,
            "full_name": "Sam Doe",
            "email": "sam@example.com",
            "password_hash": "never-sent-back",
            "created_at": datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
            **extra,
        }
    )
    return str(user_id)


def test_a_voice_verified_session_sees_the_account(client, users, voiceprints, monkeypatch):
    from cryptography.fernet import Fernet

    import config

    monkeypatch.setattr(config, "VOICEPRINT_KEY", Fernet.generate_key().decode())
    user_id = make_account(users, previous_verified_at=datetime(2026, 11, 13, 18, 30, tzinfo=UTC))
    save_voiceprint(voiceprints, user_id, [0.6, 0.8, 0.0])

    response = client.get(ME_URL, headers=bearer(create_verified_token(user_id)))

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Sam Doe"
    assert body["email"] == "sam@example.com"
    assert body["created_at"].startswith("2026-11-01T09:00")
    assert body["enrolled_at"] is not None
    assert body["previous_sign_in_at"].startswith("2026-11-13T18:30")
    # Nothing else: no ids, hashes, voiceprints or scores.
    assert set(body) == {"full_name", "email", "created_at", "enrolled_at", "previous_sign_in_at"}


def test_first_sign_in_and_not_enrolled_are_empty(client, users):
    user_id = make_account(users)

    body = client.get(ME_URL, headers=bearer(create_verified_token(user_id))).json()

    assert body["enrolled_at"] is None
    assert body["previous_sign_in_at"] is None


def test_a_password_alone_gets_403(client, users):
    user_id = make_account(users)

    response = client.get(ME_URL, headers=bearer(create_access_token(user_id)))

    assert response.status_code == 403
    assert "voice check" in response.json()["detail"]


def test_no_token_gets_401(client):
    assert client.get(ME_URL).status_code == 401


def test_a_deleted_account_gets_401(client):
    response = client.get(ME_URL, headers=bearer(create_verified_token(str(ObjectId()))))

    assert response.status_code == 401


def test_sign_in_to_account_end_to_end(client, users, challenges, voiceprints, monkeypatch):
    """Password → limited token → approved voice check → verified token → account,
    with the previous sign-in remembered."""
    from cryptography.fernet import Fernet

    import config
    from embedding import Embedding, get_embedder
    from main import app
    from transcription import get_transcriber

    monkeypatch.setattr(config, "VOICEPRINT_KEY", Fernet.generate_key().decode())
    client.post(
        "/api/auth/signup",
        json={"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"},
    )
    user_id = str(users.find_one({"email": "sam@example.com"})["_id"])
    save_voiceprint(voiceprints, user_id, [0.6, 0.8, 0.0])
    heard = {}
    app.dependency_overrides[get_transcriber] = lambda: lambda audio, filename: heard["passage"]
    app.dependency_overrides[get_embedder] = lambda: (
        lambda audio, filename: Embedding(
            vector=[0.6, 0.8, 0.0],
            speech_seconds=2.0,
            clipped_share=0.0,
            liveness_model="test",
            liveness=config.LIVENESS_THRESHOLD + 1.0,
        )
    )

    def sign_in():
        limited = client.post(
            "/api/auth/login", json={"email": "sam@example.com", "password": "correct-horse-battery"}
        ).json()["access_token"]
        assert client.get(ME_URL, headers=bearer(limited)).status_code == 403
        passage = client.post("/api/challenge", headers=bearer(limited)).json()
        heard["passage"] = passage["passage"]
        result = client.post(
            "/api/verify",
            headers=bearer(limited),
            files={"audio": ("attempt", b"speech", "audio/webm")},
            data={"attempt_id": passage["attempt_id"]},
        ).json()
        assert result["decision"] == "approved"
        return client.get(ME_URL, headers=bearer(result["access_token"]))

    first = sign_in()
    assert first.status_code == 200
    assert first.json()["previous_sign_in_at"] is None

    second = sign_in().json()
    assert second["previous_sign_in_at"] is not None
