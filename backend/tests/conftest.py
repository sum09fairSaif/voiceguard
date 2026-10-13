import secrets

import mongomock
import pytest
from fastapi.testclient import TestClient

import config
from db import get_challenges_collection, get_users_collection
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
def client(users, challenges, monkeypatch):
    # A fresh random key each run, so the code can't pass by hard-coding one.
    monkeypatch.setattr(config, "JWT_SECRET", secrets.token_urlsafe(32))
    app.dependency_overrides[get_users_collection] = lambda: users
    app.dependency_overrides[get_challenges_collection] = lambda: challenges
    yield TestClient(app)
    app.dependency_overrides.clear()
