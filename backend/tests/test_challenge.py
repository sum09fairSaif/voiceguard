from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

import config
from challenges import create_challenge, use_challenge
from db import get_challenges_collection
from main import app
from security import create_access_token

CHALLENGE_URL = "/api/challenge"
USER_ID = str(ObjectId())


def signed_in(user_id=USER_ID):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def in_one_hour():
    return datetime.now(timezone.utc) + timedelta(hours=1)


# --- Asking for a passage ---------------------------------------------------


def test_signed_in_user_gets_a_fresh_passage(client, challenges):
    before = datetime.now(timezone.utc)
    response = client.post(CHALLENGE_URL, headers=signed_in())

    assert response.status_code == 201
    body = response.json()
    assert len(body["passage"].split(" ")) == 6
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(seconds=115) < expires_at - before < timedelta(seconds=125)

    saved = challenges.find_one({"_id": ObjectId(body["attempt_id"])})
    assert saved["user_id"] == USER_ID
    assert saved["passage"] == body["passage"]
    assert saved["used"] is False


def test_each_request_gets_a_new_passage(client, challenges):
    first = client.post(CHALLENGE_URL, headers=signed_in()).json()
    second = client.post(CHALLENGE_URL, headers=signed_in()).json()

    assert first["attempt_id"] != second["attempt_id"]
    assert first["passage"] != second["passage"]
    assert challenges.count_documents({}) == 2


def test_token_from_signup_works(client, challenges):
    signup = client.post(
        "/api/auth/signup",
        json={"full_name": "Sam Lee", "email": "sam@example.com", "password": "correct-horse"},
    ).json()
    headers = {"Authorization": f"Bearer {signup['access_token']}"}
    response = client.post(CHALLENGE_URL, headers=headers)

    assert response.status_code == 201
    saved = challenges.find_one({"_id": ObjectId(response.json()["attempt_id"])})
    assert saved["user_id"] == signup["user"]["id"]


# --- Turning away people who aren't signed in -------------------------------


def test_no_token_is_refused(client, challenges):
    response = client.post(CHALLENGE_URL)

    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in first."
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert challenges.count_documents({}) == 0


@pytest.mark.parametrize(
    "make_token",
    [
        lambda: "not-a-real-token",
        lambda: jwt.encode({"sub": USER_ID, "exp": in_one_hour()}, "some-other-key-" * 3, algorithm="HS256"),
        lambda: jwt.encode({"sub": USER_ID}, config.JWT_SECRET, algorithm="HS256"),
        lambda: jwt.encode({"exp": in_one_hour()}, config.JWT_SECRET, algorithm="HS256"),
        lambda: jwt.encode({"sub": USER_ID, "exp": in_one_hour()}, None, algorithm="none"),
    ],
    ids=["garbage", "wrong-key", "no-expiry", "no-user", "unsigned"],
)
def test_invalid_token_is_refused(client, challenges, make_token):
    response = client.post(CHALLENGE_URL, headers={"Authorization": f"Bearer {make_token()}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Your login token is not valid. Please sign in again."
    assert challenges.count_documents({}) == 0


def test_expired_token_is_refused(client, challenges):
    an_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode({"sub": USER_ID, "exp": an_hour_ago}, config.JWT_SECRET, algorithm="HS256")
    response = client.post(CHALLENGE_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Your session has expired. Please sign in again."
    assert challenges.count_documents({}) == 0


class UnreachableDatabase:
    def insert_one(self, document):
        raise ServerSelectionTimeoutError("database unreachable")


def test_database_outage_returns_503(client):
    app.dependency_overrides[get_challenges_collection] = lambda: UnreachableDatabase()
    response = client.post(CHALLENGE_URL, headers=signed_in())

    assert response.status_code == 503


# --- Using an attempt later (for the voice check) ---------------------------


def test_attempt_can_be_used_once_by_its_owner(challenges):
    attempt_id = str(create_challenge(challenges, USER_ID)["_id"])
    passage = challenges.find_one()["passage"]

    assert use_challenge(challenges, attempt_id, USER_ID) == passage
    assert use_challenge(challenges, attempt_id, USER_ID) is None


def test_attempt_cannot_be_used_by_someone_else(challenges):
    attempt_id = str(create_challenge(challenges, USER_ID)["_id"])

    assert use_challenge(challenges, attempt_id, str(ObjectId())) is None
    assert use_challenge(challenges, attempt_id, USER_ID) is not None


def test_expired_attempt_cannot_be_used(challenges):
    attempt = create_challenge(challenges, USER_ID)
    challenges.update_one(
        {"_id": attempt["_id"]},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    assert use_challenge(challenges, str(attempt["_id"]), USER_ID) is None


@pytest.mark.parametrize("attempt_id", ["not-an-id", str(ObjectId())], ids=["malformed", "unknown"])
def test_unknown_attempt_cannot_be_used(challenges, attempt_id):
    assert use_challenge(challenges, attempt_id, USER_ID) is None
