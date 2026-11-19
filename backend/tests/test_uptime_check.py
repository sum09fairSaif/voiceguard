"""The uptime check's decisions (.github/scripts/check_uptime.py, #167)."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "check_uptime.py"
_spec = importlib.util.spec_from_file_location("check_uptime", _path)
uptime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uptime)

URL = "https://api.example.test"
NOW = datetime(2026, 11, 16, 9, 30, tzinfo=UTC)


class FakeGitHub:
    def __init__(self, open_outage=None):
        self.outage = open_outage
        self.calls = []

    def open_outage(self):
        return self.outage

    def open_issue(self, body):
        self.calls.append(("open", body))

    def comment(self, number, body):
        self.calls.append(("comment", number, body))

    def close(self, number):
        self.calls.append(("close", number))


def answers(*results):
    replies = list(results)
    return lambda url: replies.pop(0)


def no_wait(seconds):
    return None


def test_up_with_no_outage_does_nothing():
    github = FakeGitHub()

    assert uptime.run(URL, github, answers(True), no_wait, NOW) == "up"
    assert github.calls == []


def test_one_slow_try_then_up_is_not_an_outage():
    github = FakeGitHub()

    assert uptime.run(URL, github, answers(False, True), no_wait, NOW) == "up"
    assert github.calls == []


def test_two_failures_open_an_issue():
    github = FakeGitHub()
    waits = []

    assert uptime.run(URL, github, answers(False, False), waits.append, NOW) == "opened"
    ((kind, body),) = github.calls
    assert kind == "open"
    assert "2026-11-16 09:30 UTC" in body
    assert "docs/runbook.md" in body
    assert waits == [uptime.PAUSE_SECONDS]


def test_still_down_doesnt_open_a_second_issue():
    github = FakeGitHub(open_outage=42)

    assert uptime.run(URL, github, answers(False, False), no_wait, NOW) == "still_down"
    assert github.calls == []


def test_back_up_comments_and_closes():
    github = FakeGitHub(open_outage=42)

    assert uptime.run(URL, github, answers(True), no_wait, NOW) == "closed"
    assert github.calls[0][0:2] == ("comment", 42)
    assert github.calls[1] == ("close", 42)


@pytest.mark.parametrize("error", [OSError("refused"), TimeoutError("slow")])
def test_an_unreachable_api_counts_as_down(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(uptime.urllib.request, "urlopen", fail)

    assert uptime.api_is_up(URL) is False


def test_the_github_client_finds_only_the_outage_issue(monkeypatch):
    github = uptime.GitHub("owner/repo", "token")
    monkeypatch.setattr(
        github,
        "_call",
        lambda method, path, body=None: [
            {"number": 7, "title": "Something else"},
            {"number": 8, "title": uptime.TITLE, "pull_request": {}},
            {"number": 9, "title": uptime.TITLE},
        ],
    )

    assert github.open_outage() == 9
