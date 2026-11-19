"""Uptime check, run by .github/workflows/uptime.yml every 5 minutes.

Asks the API's /health (allowing for Render's free plan waking up, which can
take about a minute). If it fails twice in a row, opens an "API is down" issue
so everyone watching the repo is notified; when the API answers again, comments
and closes it. Standard library only, so the workflow needs no install step.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime

TITLE = "API is down (uptime check)"
TRIES = 2
PAUSE_SECONDS = 60
# Render's free instance can take about a minute to wake up.
TIMEOUT_SECONDS = 90


def api_is_up(url: str, timeout: float = TIMEOUT_SECONDS) -> bool:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def check(url: str, is_up: Callable[[str], bool] = api_is_up, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Up unless every try fails, so one slow wake-up isn't an outage."""
    for attempt in range(TRIES):
        if is_up(url):
            return True
        if attempt < TRIES - 1:
            sleep(PAUSE_SECONDS)
    return False


class GitHub:
    """The few issue calls this needs, with the workflow's own token."""

    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token

    def _call(self, method: str, path: str, body: dict | None = None):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or "null")

    def open_outage(self) -> int | None:
        for issue in self._call("GET", "/issues?state=open&per_page=100") or []:
            if issue.get("title") == TITLE and "pull_request" not in issue:
                return issue["number"]
        return None

    def open_issue(self, body: str) -> None:
        self._call("POST", "/issues", {"title": TITLE, "body": body})

    def comment(self, number: int, body: str) -> None:
        self._call("POST", f"/issues/{number}/comments", {"body": body})

    def close(self, number: int) -> None:
        self._call("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})


def run(url: str, github, is_up: Callable[[str], bool] = api_is_up, sleep=time.sleep, now=None) -> str:
    """Check once and update the outage issue. Returns what it did."""
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    up = check(url, is_up, sleep)
    outage = github.open_outage()
    if not up and outage is None:
        github.open_issue(
            f"The uptime check couldn't reach `{url}/health` ({TRIES} tries, {PAUSE_SECONDS} s apart) at {stamp}.\n\n"
            "See docs/runbook.md. This issue closes itself when the API answers again."
        )
        return "opened"
    if not up:
        return "still_down"
    if outage is not None:
        github.comment(outage, f"The API is answering again ({stamp}). Closing.")
        github.close(outage)
        return "closed"
    return "up"


if __name__ == "__main__":
    result = run(os.environ["API_URL"], GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]))
    print(f"uptime check: {result}")
    sys.exit(0)
