import secrets

import mongomock
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import audit
import config
import switches
from db import (
    get_challenges_collection,
    get_email_codes_collection,
    get_enroll_prompts_collection,
    get_enrollments_collection,
    get_login_failures_collection,
    get_rate_limits_collection,
    get_users_collection,
    get_voice_failures_collection,
    get_voiceprints_collection,
)
from email_sender import get_optional_email_sender
from main import app
from sessions import revoked_sessions


@pytest.fixture
def users():
    # A fake in-memory database, so tests never touch the real MongoDB.
    collection = mongomock.MongoClient()["voiceguard_test"]["users"]
    collection.create_index("email", unique=True)
    return collection


@pytest.fixture
def challenges():
    collection = mongomock.MongoClient()["voiceguard_test"]["challenges"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def rate_limits():
    collection = mongomock.MongoClient()["voiceguard_test"]["rate_limits"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def voiceprints(monkeypatch):
    # A fresh random encryption key each run, like JWT_SECRET below.
    monkeypatch.setattr(config, "VOICEPRINT_KEY", Fernet.generate_key().decode())
    return mongomock.MongoClient()["voiceguard_test"]["voiceprints"]


@pytest.fixture
def enrollments():
    collection = mongomock.MongoClient()["voiceguard_test"]["enrollments"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def enroll_prompts():
    collection = mongomock.MongoClient()["voiceguard_test"]["enroll_prompts"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def login_failures():
    collection = mongomock.MongoClient()["voiceguard_test"]["login_failures"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def voice_failures():
    collection = mongomock.MongoClient()["voiceguard_test"]["voice_failures"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def email_codes():
    collection = mongomock.MongoClient()["voiceguard_test"]["email_codes"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def switch_store():
    return mongomock.MongoClient()["voiceguard_test"]["switches"]


@pytest.fixture(autouse=True)
def in_memory_switches(switch_store):
    # Every app in the tests reads switches from an in-memory collection,
    # with nothing cached from an earlier test.
    switches._cache.clear()
    app.dependency_overrides[switches.switches_store] = lambda: (lambda: switch_store)
    yield
    app.dependency_overrides.pop(switches.switches_store, None)
    switches._cache.clear()


@pytest.fixture
def revoked():
    collection = mongomock.MongoClient()["voiceguard_test"]["revoked_sessions"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture(autouse=True)
def no_real_revocation_store(revoked):
    # Every app in the tests checks sign-outs against an in-memory list.
    app.dependency_overrides[revoked_sessions] = lambda: (lambda: revoked)
    yield
    app.dependency_overrides.pop(revoked_sessions, None)


@pytest.fixture
def audit_events(monkeypatch):
    # Security events go to an in-memory collection; PostHog is never called.
    collection = mongomock.MongoClient()["voiceguard_test"]["audit_events"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    monkeypatch.setattr(audit, "_collection", lambda: collection)
    monkeypatch.setattr(config, "POSTHOG_API_KEY", "")
    return collection


@pytest.fixture(autouse=True)
def _audit_in_memory(audit_events):
    yield


@pytest.fixture
def client(
    users, challenges, rate_limits, voiceprints, enrollments, enroll_prompts, login_failures, voice_failures,
    email_codes, monkeypatch,
):
    # A fresh random key each run, so the code can't pass by hard-coding one.
    monkeypatch.setattr(config, "JWT_SECRET", secrets.token_urlsafe(32))
    # Details on, whatever a local .env says: most tests check them. The
    # live default is off (see test_verify.py); tests that hide them say so.
    monkeypatch.setattr(config, "VERIFY_CHECK_DETAILS", True)
    # Limits count in fixed blocks of time (rate_limit.py). With the real
    # hour, a test whose requests straddle hh:00:00 splits its count across
    # two windows and isn't refused when it should be. These windows' edges
    # fall in 2001 and 2033, never during a run. test_rate_limit.py checks
    # the real windows with fixed times.
    monkeypatch.setattr(config, "RATE_LIMIT_WINDOW_SECONDS", 10**9)
    app.dependency_overrides[get_users_collection] = lambda: users
    app.dependency_overrides[get_challenges_collection] = lambda: challenges
    app.dependency_overrides[get_rate_limits_collection] = lambda: rate_limits
    app.dependency_overrides[get_voiceprints_collection] = lambda: voiceprints
    app.dependency_overrides[get_enrollments_collection] = lambda: enrollments
    app.dependency_overrides[get_enroll_prompts_collection] = lambda: enroll_prompts
    app.dependency_overrides[get_login_failures_collection] = lambda: login_failures
    app.dependency_overrides[get_voice_failures_collection] = lambda: voice_failures
    app.dependency_overrides[get_email_codes_collection] = lambda: email_codes
    # Tests never send real email; test_email_verification.py records it.
    app.dependency_overrides[get_optional_email_sender] = lambda: None
    # Verification stays off unless a test turns it on, as in production.
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", False)
    yield TestClient(app)
    app.dependency_overrides.clear()
