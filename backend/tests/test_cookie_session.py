"""The sign-in token as an HttpOnly cookie, and the cross-site request check (#102)."""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import config
from embedding import Embedding, get_embedder
from main import app
from security import create_access_token
from session_cookie import cookie_name
from transcription import get_transcriber
from voiceprints import save_voiceprint

OURS = "https://voiceguard-nu.vercel.app"
EVIL = "https://evil.example"
EMAIL, PASSWORD = "sam@example.com", "correct-horse-battery"
SIGNUP = {"full_name": "Sam Doe", "email": EMAIL, "password": PASSWORD}


@pytest.fixture
def browser(client):
    """Like a browser on our own page: HTTPS (Secure cookies are only sent
    over it), keeps cookies, and says where each request comes from."""
    return TestClient(app, base_url="https://testserver", headers={"Origin": OURS})


def set_cookie_header(response) -> str:
    [header] = [v for k, v in response.headers.multi_items() if k == "set-cookie" and cookie_name() in v]
    return header


def sign_up(browser):
    return browser.post("/api/auth/signup", json=SIGNUP)


def sign_in(browser):
    return browser.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})


# --- The cookie itself -----------------------------------------------------------


@pytest.mark.parametrize("action", [sign_up, lambda b: (sign_up(b), sign_in(b))[1]], ids=["signup", "login"])
def test_signing_up_or_in_sets_a_cookie_scripts_cant_read(browser, action):
    response = action(browser)

    header = set_cookie_header(response).lower()
    assert header.startswith(f"{cookie_name().lower()}=")
    for flag in ("httponly", "secure", "samesite=strict", "path=/", f"max-age={config.JWT_EXPIRE_MINUTES * 60}"):
        assert flag in header
    # __Host- cookies may not name a domain: only this exact host gets it.
    assert "domain=" not in header


def test_the_cookie_name_is_host_locked():
    assert cookie_name() == "__Host-voiceguard_session"


def test_with_the_cookie_alone_the_voice_check_steps_work(browser):
    sign_up(browser)

    # No Authorization header: only the cookie.
    assert browser.post("/api/challenge").status_code == 201
    assert browser.get("/api/enroll").status_code == 200


def test_without_the_body_setting_no_token_reaches_the_page(browser, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_IN_RESPONSE_BODY", False)

    body = sign_up(browser).json()

    assert body["access_token"] is None
    assert browser.post("/api/challenge").status_code == 201


def test_during_the_change_over_the_token_is_still_in_the_body(browser):
    assert sign_up(browser).json()["access_token"]


def test_a_bearer_header_still_works(client, users):
    client.post("/api/auth/signup", json=SIGNUP)
    token = create_access_token(str(users.find_one({"email": EMAIL})["_id"]), source="signup")

    assert client.post("/api/challenge", headers={"Authorization": f"Bearer {token}"}).status_code == 201


def test_a_bad_cookie_is_refused(browser):
    browser.cookies.set(cookie_name(), "not-a-token")

    assert browser.post("/api/challenge").status_code == 401


# --- Approval and sign-out ------------------------------------------------------------


def test_an_approved_voice_check_swaps_in_the_voice_verified_cookie(browser, users, voiceprints, monkeypatch):
    monkeypatch.setattr(config, "VOICEPRINT_KEY", Fernet.generate_key().decode())
    sign_up(browser)
    save_voiceprint(voiceprints, str(users.find_one({"email": EMAIL})["_id"]), [0.6, 0.8, 0.0])
    heard = {}
    app.dependency_overrides[get_transcriber] = lambda: lambda audio, filename: heard["passage"]
    app.dependency_overrides[get_embedder] = lambda: lambda audio, filename: Embedding(
        vector=[0.6, 0.8, 0.0], speech_seconds=2.0, clipped_share=0.0, liveness_model="test",
        liveness=config.LIVENESS_THRESHOLD + 1.0,
    )
    assert browser.get("/api/me").status_code == 403  # password only so far

    passage = browser.post("/api/challenge").json()
    heard["passage"] = passage["passage"]
    result = browser.post(
        "/api/verify", files={"audio": ("a", b"speech", "audio/webm")}, data={"attempt_id": passage["attempt_id"]}
    )

    assert result.json()["decision"] == "approved"
    assert f"max-age={config.VERIFIED_TOKEN_MINUTES * 60}" in set_cookie_header(result).lower()
    assert browser.get("/api/me").status_code == 200


def test_signing_out_clears_the_cookie_and_ends_the_session(browser):
    sign_up(browser)
    old = browser.cookies.get(cookie_name())

    response = browser.post("/api/auth/logout")

    assert response.status_code == 204
    header = set_cookie_header(response).lower()
    assert 'max-age=0' in header or "expires=thu, 01 jan 1970" in header
    assert cookie_name() not in browser.cookies
    # A copy of the old cookie no longer works either.
    browser.cookies.set(cookie_name(), old)
    assert browser.post("/api/challenge").status_code == 401


def test_signing_out_with_a_dead_cookie_still_clears_it(browser):
    browser.cookies.set(cookie_name(), "expired-or-garbage", domain="testserver.local")

    response = browser.post("/api/auth/logout")

    assert response.status_code == 401
    assert cookie_name() in set_cookie_header(response)
    assert cookie_name() not in browser.cookies


# --- Cross-site request forgery ---------------------------------------------------------


def test_a_request_from_another_site_is_refused_even_with_the_cookie(browser):
    sign_up(browser)

    response = browser.post("/api/challenge", headers={"Origin": EVIL})

    assert response.status_code == 403
    assert response.json()["detail"].startswith("This request didn't come from VoiceGuard.")


def test_a_cookie_without_an_origin_is_refused_on_changes(browser):
    sign_up(browser)
    browser.headers.pop("Origin")

    assert browser.post("/api/challenge").status_code == 403
    # Reading is fine: GET doesn't change anything.
    assert browser.get("/api/enroll").status_code == 200


def test_another_site_cant_sign_someone_in(browser):
    # A forged sign-in would put the victim in the attacker's account.
    sign_up(browser)

    response = browser.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers={"Origin": EVIL})

    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_preview_deployments_count_as_ours(browser):
    preview = "https://voiceguard-git-some-branch-voice-guard2.vercel.app"

    assert sign_up(browser).status_code == 201
    assert browser.post("/api/challenge", headers={"Origin": preview}).status_code == 201


def test_scripts_without_cookie_or_origin_are_unaffected(client):
    # No browser sends neither; API scripts and tests with a header do.
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 201
