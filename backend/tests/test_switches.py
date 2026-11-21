"""Pause switches (#163)."""

import pytest
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

import config
import switches
from security import create_access_token
from switches import CACHE_SECONDS, is_on, set_switch

USER_ID = str(ObjectId())


def signed_in():
    return {"Authorization": f"Bearer {create_access_token(USER_ID)}"}


def turn_off(store, name):
    set_switch(store, name, False, by="tester", reason="test")
    switches._cache.clear()


ROUTES = {
    "signups": lambda c: c.post(
        "/api/auth/signup",
        json={"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"},
    ),
    "voice_checks": lambda c: c.post("/api/challenge", headers=signed_in()),
    "enrollment": lambda c: c.post(
        "/api/enroll/samples", headers=signed_in(), files={"audio": ("sample", b"speech", "audio/webm")}
    ),
}


@pytest.mark.parametrize("name", switches.NAMES)
def test_everything_is_on_until_turned_off(name):
    assert is_on(name, lambda: _empty())


def _empty():
    import mongomock

    return mongomock.MongoClient()["t"]["switches"]


@pytest.mark.parametrize("name", switches.NAMES)
def test_a_switched_off_route_says_its_paused(client, switch_store, name):
    turn_off(switch_store, name)

    response = ROUTES[name](client)

    assert response.status_code == 503
    assert response.json() == {"detail": switches.PAUSED_MESSAGES[name], "paused": name}


def test_voice_checks_pause_covers_the_check_itself(client, switch_store):
    turn_off(switch_store, "voice_checks")

    response = client.post(
        "/api/verify",
        headers=signed_in(),
        files={"audio": ("attempt", b"speech", "audio/webm")},
        data={"attempt_id": str(ObjectId())},
    )

    assert response.status_code == 503
    assert response.json()["paused"] == "voice_checks"


def test_one_switch_leaves_the_others_alone(client, switch_store, new_account):
    # A token is refused once its account is gone (#194).
    new_account(USER_ID)
    turn_off(switch_store, "signups")

    assert client.post("/api/challenge", headers=signed_in()).status_code == 201


def test_sign_in_is_never_paused(client, switch_store):
    for name in switches.NAMES:
        turn_off(switch_store, name)

    response = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})

    assert response.status_code == 401


def test_a_pause_does_no_work(client, switch_store, users):
    turn_off(switch_store, "signups")

    ROUTES["signups"](client)

    assert users.count_documents({}) == 0


def test_a_change_is_picked_up_within_the_cache_window(switch_store):
    assert is_on("signups", lambda: switch_store, now=1000.0)
    set_switch(switch_store, "signups", False, by="tester", reason="test")

    # Still the cached value just before the window ends, the new one after.
    assert is_on("signups", lambda: switch_store, now=1000.0 + CACHE_SECONDS - 1)
    assert not is_on("signups", lambda: switch_store, now=1000.0 + CACHE_SECONDS)


@pytest.mark.parametrize(
    ("name", "setting"),
    [("signups", "SIGNUPS_ENABLED"), ("voice_checks", "VOICE_CHECKS_ENABLED"), ("enrollment", "ENROLLMENT_ENABLED")],
)
def test_a_setting_forces_a_switch_off(client, monkeypatch, name, setting):
    monkeypatch.setattr(config, setting, False)

    assert ROUTES[name](client).status_code == 503


def test_an_unreadable_store_keeps_the_last_value(switch_store):
    class Unreachable:
        def find_one(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("database unreachable")

    set_switch(switch_store, "signups", False, by="tester", reason="test")
    assert not is_on("signups", lambda: switch_store, now=0.0)

    assert not is_on("signups", lambda: Unreachable(), now=CACHE_SECONDS + 1.0)


def test_an_unreadable_store_with_nothing_seen_counts_as_on():
    class Unreachable:
        def find_one(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("database unreachable")

    assert is_on("enrollment", lambda: Unreachable(), now=0.0)


def test_flipping_keeps_who_when_and_why(switch_store):
    set_switch(switch_store, "enrollment", False, by="Gabriel", reason="spike in model-service errors")

    record = switch_store.find_one({"_id": "enrollment"})
    assert record["on"] is False
    assert record["changed_by"] == "Gabriel"
    assert record["reason"] == "spike in model-service errors"
    assert record["changed_at"] is not None


def test_unknown_switch_names_are_refused(switch_store):
    with pytest.raises(ValueError, match="Unknown switch"):
        set_switch(switch_store, "logins", False, by="x", reason="y")
