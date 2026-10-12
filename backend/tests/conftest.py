import mongomock
import pytest
from fastapi.testclient import TestClient

import config
from db import get_users_collection
from main import app


@pytest.fixture
def users():
    # A fake in-memory database, so tests never touch the real MongoDB.
    collection = mongomock.MongoClient()["voiceguard_test"]["users"]
    collection.create_index("email", unique=True)
    return collection


@pytest.fixture
def client(users, monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret")
    app.dependency_overrides[get_users_collection] = lambda: users
    yield TestClient(app)
    app.dependency_overrides.clear()
