"""Which passwords signup accepts (NIST SP 800-63B-4, #161)."""

import pytest

import password_policy
from password_policy import MIN_LENGTH, password_problem

EMAIL = "sam.doe@example.com"
SIGNUP_URL = "/api/auth/signup"


def not_listed(password):
    # Pattern tests use passwords that aren't on the breach list, so each
    # rule is shown working on its own.
    assert password.lower() not in password_policy._common()
    return password


def test_the_list_is_bundled_and_holds_only_long_entries():
    common = password_policy._common()

    assert len(common) > 5000
    assert all(len(entry) >= MIN_LENGTH for entry in common)
    assert all(entry == entry.lower() for entry in common)


def test_the_list_is_read_once():
    assert password_policy._common() is password_policy._common()


def test_a_listed_password_is_refused_in_any_case():
    listed = sorted(password_policy._common())[1000]

    assert password_problem(listed) == "common"
    assert password_problem(listed.upper()) == "common"


def test_a_password_that_merely_contains_a_listed_one_is_fine():
    listed = sorted(password_policy._common())[1000]

    assert password_problem(f"my {listed} and more") is None


@pytest.mark.parametrize(
    "password",
    ["correct horse battery staple", "Tr0ub4dor&3-plus-more", "lantern-orchid-41-tide", "ÉtéÀParis2026-voyage"],
)
def test_good_passwords_are_accepted(password):
    assert password_problem(not_listed(password), EMAIL) is None


@pytest.mark.parametrize(
    "password",
    ["VoiceGuard2026!!#", "voice-guard-voice-guard", "samdoe1234567890", "Sam.Doe.Sam.Doe.!", "SAMDOE!!!!!!!!!!!"],
)
def test_the_apps_or_the_persons_own_name_is_refused(password):
    assert password_problem(not_listed(password), EMAIL) == "personal"


@pytest.mark.parametrize(
    "password", ["mmmmmmmmmmmmmmmmm", "xyzzyxyzzyxyzzyxyzzy", "horsebatteryhorsebattery", "ab!ab!ab!ab!ab!ab!"]
)
def test_one_chunk_repeated_is_refused(password):
    assert password_problem(not_listed(password)) == "repetitive"


@pytest.mark.parametrize(
    "password", ["fghijklmnopqrstuvw", "34567890123456789", "rqponmlkjihgfedcb", "tyuiopasdfghjklzx"]
)
def test_sequences_and_keyboard_runs_are_refused(password):
    assert password_problem(not_listed(password)) == "sequential"


# --- Through signup -------------------------------------------------------------


def signup(client, password, email="sam@example.com"):
    return client.post(SIGNUP_URL, json={"full_name": "Sam Doe", "email": email, "password": password})


def test_signup_needs_15_characters(client):
    assert signup(client, "a-good-pass-14").status_code == 422
    assert signup(client, "a-good-pass-15!").status_code == 201


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("mmmmmmmmmmmmmmmmm", "password_repetitive"),
        ("fghijklmnopqrstuvw", "password_sequential"),
        ("VoiceGuard2026!!#", "password_personal"),
        ("samsamsamsamsamsam", "password_personal"),  # the email name, repeated
    ],
)
def test_signup_says_why_a_password_was_refused(client, users, password, problem):
    response = signup(client, password)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "password"]
    assert error["type"] == problem
    assert password not in response.text
    assert users.count_documents({}) == 0


def test_signup_refuses_a_breached_password(client):
    listed = sorted(password_policy._common())[2000]

    response = signup(client, listed)

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "password_common"


def test_the_email_name_rule_uses_the_signup_email(client):
    assert signup(client, "jordan-rivers-2026!", email="jordan.rivers@example.com").json()["detail"][0]["type"] == (
        "password_personal"
    )
    assert signup(client, "jordan-rivers-2026!", email="alex@example.com").status_code == 201


def test_sign_in_doesnt_apply_the_new_rule(client, users):
    # Existing passwords keep working: the rule is only for setting one.
    from datetime import UTC, datetime

    from security import hash_password

    users.insert_one(
        {
            "full_name": "Old",
            "email": "old@example.com",
            "password_hash": hash_password("short1"),
            "created_at": datetime.now(UTC),
        }
    )

    response = client.post("/api/auth/login", json={"email": "old@example.com", "password": "short1"})

    assert response.status_code == 200
