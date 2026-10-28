import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def preflight(origin: str):
    # What a browser sends before a cross-site POST, to ask if it's allowed.
    return client.options(
        "/api/auth/signup",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "https://voiceguard-nu.vercel.app",
        # Vercel preview deployments, per branch and per commit.
        "https://voiceguard-git-feat-19-result-screen-voice-guard2.vercel.app",
        "https://voiceguard-a1b2c3d4e-voice-guard2.vercel.app",
    ],
)
def test_our_frontends_may_call_the_api(origin):
    response = preflight(origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "https://voiceguard-nu.vercel.app.evil.example",
        "https://voiceguard-git-main-someone-else.vercel.app",
        "http://voiceguard-git-main-voice-guard2.vercel.app",
    ],
)
def test_other_websites_may_not(origin):
    response = preflight(origin)

    assert "access-control-allow-origin" not in response.headers


def test_our_frontend_may_read_retry_after():
    # Without this the browser hides Retry-After, and lockout and rate-limit
    # messages can't say how long to wait.
    response = client.get("/health", headers={"Origin": "https://voiceguard-nu.vercel.app"})

    assert response.headers["access-control-expose-headers"] == "Retry-After"
