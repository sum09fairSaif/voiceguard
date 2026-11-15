import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from body_limit import DEFAULT_LIMIT
from main import app, docs_settings
from security_headers import SECURITY_HEADERS

client = TestClient(app)

ORIGIN = "https://voiceguard-nu.vercel.app"
EXPECTED = {name.decode(): value.decode() for name, value in SECURITY_HEADERS}


def assert_security_headers(response):
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_are_off_by_default(path):
    if config.DOCS_ENABLED:
        pytest.skip("DOCS_ENABLED=true in this environment's .env")
    assert client.get(path).status_code == 404
    assert TestClient(FastAPI(**docs_settings(False))).get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_can_be_turned_on(path):
    local = FastAPI(**docs_settings(True))

    assert TestClient(local).get(path).status_code == 200


@pytest.mark.parametrize(
    ("value", "enabled"),
    [("true", True), ("TRUE", True), (" true ", True), ("", False), ("false", False), ("1", False), ("yes", False)],
)
def test_only_true_turns_docs_on(value, enabled):
    assert config.is_true(value) is enabled


def test_health_answers_head():
    response = client.head("/health")

    assert response.status_code == 200
    assert response.content == b""


def test_security_headers_on_a_success():
    assert_security_headers(client.get("/health"))


def test_security_headers_on_an_error():
    # A body that isn't JSON is refused before any setting or database is needed.
    response = client.post("/api/auth/login", content=b"not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert_security_headers(response)


def test_security_headers_on_a_refused_sign_in():
    response = client.get("/api/enroll")

    assert response.status_code == 401
    assert_security_headers(response)


def test_security_headers_on_a_refused_upload():
    response = client.post("/api/auth/login", content=b"x" * (DEFAULT_LIMIT + 1))

    assert response.status_code == 413
    assert_security_headers(response)


def test_security_headers_on_an_unknown_route():
    response = client.get("/nothing-here")

    assert response.status_code == 404
    assert_security_headers(response)


def test_security_headers_on_a_cors_preflight():
    response = client.options("/api/auth/login", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert_security_headers(response)


def test_headers_are_not_duplicated():
    response = client.get("/health")

    assert len(response.headers.get_list("cache-control")) == 1
