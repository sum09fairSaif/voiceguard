"""The security event record (#167)."""

from datetime import UTC, timedelta

import pytest
from pymongo.errors import ServerSelectionTimeoutError

import audit
import config
from audit import EVENTS, hashed, track

SIGNUP = {"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"}
LOGIN = {"email": "sam@example.com", "password": "correct-horse-battery"}


def events(store, name=None):
    query = {"event": name} if name else {}
    return list(store.find(query, {"_id": 0}))


# --- What a record holds -------------------------------------------------------


def test_a_record_holds_only_the_fixed_fields(audit_events):
    track("login_succeeded", "64b000000000000000000001", reason="test")

    (record,) = events(audit_events)
    assert set(record) == {"at", "event", "user", "reason", "expires_at"}
    assert record["user"] == hashed("64b000000000000000000001")
    assert "64b000000000000000000001" not in str(record)


def test_user_ids_are_hashed_and_stable():
    assert hashed("abc") == hashed("abc")
    assert hashed("abc") != hashed("abd")
    assert len(hashed("abc")) == 16
    assert hashed(None) is None


def test_records_expire_after_the_retention_period(audit_events):
    track("signup", "u1")

    (record,) = events(audit_events)
    kept = record["expires_at"].replace(tzinfo=UTC) - record["at"].replace(tzinfo=UTC)
    assert kept == timedelta(days=config.AUDIT_RETENTION_DAYS)
    assert any(index.get("expireAfterSeconds") == 0 for index in audit_events.index_information().values())


def test_only_known_events_are_recorded(audit_events, caplog):
    track("something_made_up", "u1")

    assert events(audit_events) == []
    assert "audit_not_recorded" in caplog.text


def test_track_takes_no_free_form_fields():
    with pytest.raises(TypeError):
        track("signup", "u1", email="sam@example.com")


def test_a_database_failure_never_fails_the_caller(monkeypatch, caplog):
    class Unreachable:
        def insert_one(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("database unreachable")

    monkeypatch.setattr(audit, "_collection", lambda: Unreachable())

    track("signup", "u1")  # no exception

    assert "audit_not_recorded where=database event=signup" in caplog.text


# --- PostHog --------------------------------------------------------------------


def test_nothing_leaves_the_server_without_a_posthog_key(monkeypatch):
    sent = []
    monkeypatch.setattr(audit, "_enqueue", lambda *args: sent.append(args))

    track("signup", "u1")

    assert sent == []


def test_with_a_key_the_same_event_goes_to_posthog_in_the_background(monkeypatch):
    sent = []
    monkeypatch.setattr(config, "POSTHOG_API_KEY", "phc_test")
    monkeypatch.setattr(audit, "_enqueue", lambda *args: sent.append(args))

    track("voice_check_rejected", "u1", reason="voice")

    assert sent == [("voice_check_rejected", hashed("u1"), "voice")]


def test_the_posthog_payload_holds_no_personal_data(monkeypatch):
    posted = {}
    monkeypatch.setattr(config, "POSTHOG_API_KEY", "phc_test")

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, json):
        posted.update(url=url, json=json)
        return Response()

    monkeypatch.setattr(audit._http, "post", fake_post)

    audit._send_to_posthog("login_failed", hashed("u1"), "wrong_password")

    assert posted["url"] == "https://us.i.posthog.com/capture/"
    assert audit._http.timeout.read == 2.0
    assert posted["json"]["distinct_id"] == hashed("u1")
    assert posted["json"]["properties"] == {"reason": "wrong_password", "source": "backend"}


def test_a_posthog_failure_is_only_logged(monkeypatch, caplog):
    monkeypatch.setattr(config, "POSTHOG_API_KEY", "phc_test")

    def unreachable(*args, **kwargs):
        raise audit.httpx.ConnectError("unreachable")

    monkeypatch.setattr(audit._http, "post", unreachable)

    audit._send_to_posthog("signup", None, None)  # no exception

    assert "audit_not_recorded where=posthog event=signup" in caplog.text


def test_queued_events_are_sent_by_the_background_thread(monkeypatch):
    import threading

    delivered = threading.Event()
    sent = []

    def fake_send(*args):
        sent.append(args)
        delivered.set()

    monkeypatch.setattr(audit, "_send_to_posthog", fake_send)

    audit._enqueue("signup", hashed("u1"), None)

    assert delivered.wait(2)
    assert sent == [("signup", hashed("u1"), None)]


def test_a_full_queue_drops_events_with_a_log_line_instead_of_growing(monkeypatch, caplog):
    import queue

    small = queue.Queue(maxsize=2)
    monkeypatch.setattr(audit, "_queue", small)
    monkeypatch.setattr(audit, "_dropped", 0)
    # A worker that's busy (never takes from the queue), as in a flood.
    monkeypatch.setattr(audit, "_worker", type("Busy", (), {"is_alive": lambda self: True})())

    for _ in range(5):
        audit._enqueue("login_failed", None, "wrong_password")

    assert small.qsize() == 2
    assert audit._dropped == 3
    # Logged once for the first drop, not once per drop.
    assert caplog.text.count("where=posthog_queue_full") == 1


def test_the_queue_has_a_limit():
    assert 0 < audit._queue.maxsize == audit.QUEUE_LIMIT <= 10_000


# --- The user-id stand-in is keyed (Sumehra's review on #168) ------------------


def test_the_stand_in_needs_the_server_secret(monkeypatch):
    import hashlib

    user_id = "64b000000000000000000001"
    monkeypatch.setattr(config, "JWT_SECRET", "secret-one")
    first = hashed(user_id)

    # A plain hash of the id (what anyone could compute) doesn't match it...
    assert first != hashlib.sha256(user_id.encode()).hexdigest()[:16]
    # ...and another server secret gives another stand-in.
    monkeypatch.setattr(config, "JWT_SECRET", "secret-two")
    assert hashed(user_id) != first


def test_the_database_write_has_a_short_deadline(monkeypatch, audit_events):
    from pymongo import _csot  # where pymongo.timeout() keeps the current deadline

    seen = []

    class Watching:
        def insert_one(self, document):
            seen.append(_csot.get_timeout())

    monkeypatch.setattr(audit, "_collection", lambda: Watching())

    track("signup", "u1")

    assert seen and 0 < seen[0] <= audit.WRITE_SECONDS


# --- From the routes --------------------------------------------------------------


def test_signup_and_sign_in_are_recorded(client, audit_events):
    client.post("/api/auth/signup", json=SIGNUP)
    client.post("/api/auth/login", json={**LOGIN, "password": "wrong-horse-battery"})
    client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-horse-battery"})
    token = client.post("/api/auth/login", json=LOGIN).json()["access_token"]
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    recorded = [(e["event"], e["reason"]) for e in events(audit_events)]
    assert recorded == [
        ("signup", None),
        ("login_failed", "wrong_password"),
        ("login_failed", "unknown_account"),
        ("login_succeeded", None),
        ("logout", None),
    ]
    assert "sam@example.com" not in str(events(audit_events))


def test_signup_and_sign_in_give_the_browser_the_same_stand_in_as_the_security_events(client, audit_events):
    # The browser's analytics identifies people by this (#170), so its events
    # and the server's can be linked without either holding the account id.
    signed_up = client.post("/api/auth/signup", json=SIGNUP).json()["user"]
    signed_in = client.post("/api/auth/login", json=LOGIN).json()["user"]

    assert signed_up["analytics_id"] == signed_in["analytics_id"] == hashed(signed_up["id"])
    assert signed_up["analytics_id"] != signed_up["id"]
    assert [e["user"] for e in events(audit_events, "signup")] == [signed_up["analytics_id"]]


def test_a_lockout_is_recorded(client, audit_events):
    client.post("/api/auth/signup", json=SIGNUP)
    for _ in range(config.LOGIN_MAX_FAILURES + 1):
        client.post("/api/auth/login", json={**LOGIN, "password": "wrong-horse-battery"})

    assert [e["reason"] for e in events(audit_events, "login_locked")] == ["wrong_password"]
    assert events(audit_events, "login_failed")[-1]["reason"] == "locked"


def test_every_event_name_is_one_the_record_accepts():
    assert {"signup", "login_succeeded", "login_failed", "login_locked", "logout"} <= EVENTS
