"""GET /api/activity: a user's own security events, only for a voice-verified session."""

from datetime import UTC, datetime, timedelta

from bson import ObjectId

import audit
import config
from audit import hashed
from security import create_access_token, create_verified_token

ACTIVITY_URL = "/api/activity"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_account(users):
    user_id = ObjectId()
    users.insert_one(
        {
            "_id": user_id,
            "full_name": "Sam Doe",
            "email": "sam@example.com",
            "password_hash": "never-sent-back",
            "created_at": datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
        }
    )
    return str(user_id)


def record(audit_events, user_id, event, minutes_ago, reason=None):
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    audit_events.insert_one(
        {
            "at": at,
            "event": event,
            "user": hashed(user_id),
            "reason": reason,
            "expires_at": at + timedelta(days=config.AUDIT_RETENTION_DAYS),
        }
    )


def get_activity(client, user_id):
    return client.get(ACTIVITY_URL, headers=bearer(create_verified_token(user_id, "session-1")))


def test_shows_the_users_own_events_newest_first(client, users, audit_events):
    user_id = make_account(users)
    record(audit_events, user_id, "signup", 30)
    record(audit_events, user_id, "enrolled", 20)
    record(audit_events, user_id, "login_succeeded", 10)
    record(audit_events, user_id, "voice_check_approved", 5, reason="all")

    response = get_activity(client, user_id)

    assert response.status_code == 200
    events = response.json()["events"]
    assert [e["kind"] for e in events] == ["voice_check_approved", "login_succeeded", "enrolled", "signup"]
    # What happened and when, nothing else: no reason, user id or hash.
    assert all(set(e) == {"kind", "at"} for e in events)
    assert events[0]["at"].endswith(("Z", "+00:00"))


def test_never_says_which_voice_check_failed(client, users, audit_events):
    # A rejected check's reason names the failed check (#112 keeps it hidden).
    user_id = make_account(users)
    record(audit_events, user_id, "voice_check_rejected", 1, reason="liveness")

    body = get_activity(client, user_id).text

    assert "voice_check_rejected" in body
    assert "liveness" not in body


def test_shows_password_reset_requests_and_resets(client, users, audit_events):
    # A reset link asked for by someone else, or a reset the user didn't
    # make, is what they need to spot.
    user_id = make_account(users)
    record(audit_events, user_id, "password_reset_requested", 10)
    record(audit_events, user_id, "password_reset", 5)

    events = get_activity(client, user_id).json()["events"]

    assert [e["kind"] for e in events] == ["password_reset", "password_reset_requested"]


def test_shows_wrong_passwords_typed_for_the_account_by_anyone(client, users, audit_events):
    user_id = make_account(users)
    record(audit_events, user_id, "login_failed", 3, reason="wrong_password")
    record(audit_events, user_id, "login_locked", 2, reason="client")

    kinds = [e["kind"] for e in get_activity(client, user_id).json()["events"]]

    assert kinds == ["login_locked", "login_failed"]


def test_leaves_out_other_accounts_and_each_enrollment_sample(client, users, audit_events):
    user_id = make_account(users)
    someone_else = str(ObjectId())
    record(audit_events, someone_else, "login_succeeded", 1)
    record(audit_events, None, "login_failed", 1)
    record(audit_events, user_id, "enroll_sample_accepted", 2)
    record(audit_events, user_id, "enroll_sample_refused", 2, reason="too_quiet")
    record(audit_events, user_id, "enrolled", 1)

    kinds = [e["kind"] for e in get_activity(client, user_id).json()["events"]]

    assert kinds == ["enrolled"]


def test_leaves_out_events_past_the_retention_period(client, users, audit_events):
    # MongoDB deletes expired events within about a minute; until then they
    # must not show.
    user_id = make_account(users)
    record(audit_events, user_id, "signup", minutes_ago=(config.AUDIT_RETENTION_DAYS + 1) * 24 * 60)
    record(audit_events, user_id, "login_succeeded", 1)

    kinds = [e["kind"] for e in get_activity(client, user_id).json()["events"]]

    assert kinds == ["login_succeeded"]


def test_shows_at_most_the_newest_fifty(client, users, audit_events):
    user_id = make_account(users)
    for minutes in range(audit.ACTIVITY_LIMIT + 5):
        record(audit_events, user_id, "login_succeeded", minutes)

    events = get_activity(client, user_id).json()["events"]

    assert len(events) == audit.ACTIVITY_LIMIT


def test_an_account_with_no_events_gets_an_empty_list(client, users):
    user_id = make_account(users)

    assert get_activity(client, user_id).json() == {"events": []}


def test_every_shown_event_is_one_the_api_can_send():
    # A shown event the response model doesn't allow would fail every request.
    from typing import get_args

    from schemas import ActivityKind

    assert set(get_args(ActivityKind)) == audit.SHOWN_TO_USER
    assert audit.SHOWN_TO_USER <= audit.EVENTS


def test_a_password_alone_gets_403(client, users):
    user_id = make_account(users)

    response = client.get(ACTIVITY_URL, headers=bearer(create_access_token(user_id)))

    assert response.status_code == 403


def test_no_token_gets_401(client):
    assert client.get(ACTIVITY_URL).status_code == 401


def test_a_deleted_account_gets_401(client):
    response = client.get(ACTIVITY_URL, headers=bearer(create_verified_token(str(ObjectId()), "session-1")))

    assert response.status_code == 401
