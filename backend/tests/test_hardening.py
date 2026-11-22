import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from body_limit import DEFAULT_LIMIT
from main import VoiceGuardAPI, app, docs_settings
from security_headers import SECURITY_HEADERS

client = TestClient(app)

ORIGIN = "https://app.get-voiceguard.tech"
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


def test_the_real_app_follows_the_setting():
    expected = docs_settings(config.DOCS_ENABLED)
    assert (app.docs_url, app.redoc_url, app.openapi_url) == (
        expected["docs_url"],
        expected["redoc_url"],
        expected["openapi_url"],
    )


def test_the_docs_pages_can_load_their_scripts_when_on(monkeypatch):
    monkeypatch.setattr(config, "DOCS_ENABLED", True)
    local = TestClient(VoiceGuardAPI(**docs_settings(True)))

    response = local.get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_the_docs_paths_keep_the_strict_policy_when_off():
    assert "content-security-policy" in client.get("/docs").headers


def test_an_unexpected_500_still_carries_the_headers():
    crashing = VoiceGuardAPI()

    @crashing.get("/boom")
    def boom():
        raise RuntimeError("unexpected")

    response = TestClient(crashing, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert_security_headers(response)


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
