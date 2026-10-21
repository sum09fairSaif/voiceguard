import secrets

import mongomock
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import config
from db import (
    get_challenges_collection,
    get_enrollments_collection,
    get_login_failures_collection,
    get_rate_limits_collection,
    get_users_collection,
    get_voiceprints_collection,
)
from main import app


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
def login_failures():
    collection = mongomock.MongoClient()["voiceguard_test"]["login_failures"]
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection


@pytest.fixture
def client(users, challenges, rate_limits, voiceprints, enrollments, login_failures, monkeypatch):
    # A fresh random key each run, so the code can't pass by hard-coding one.
    monkeypatch.setattr(config, "JWT_SECRET", secrets.token_urlsafe(32))
    app.dependency_overrides[get_users_collection] = lambda: users
    app.dependency_overrides[get_challenges_collection] = lambda: challenges
    app.dependency_overrides[get_rate_limits_collection] = lambda: rate_limits
    app.dependency_overrides[get_voiceprints_collection] = lambda: voiceprints
    app.dependency_overrides[get_enrollments_collection] = lambda: enrollments
    app.dependency_overrides[get_login_failures_collection] = lambda: login_failures
    yield TestClient(app)
    app.dependency_overrides.clear()
