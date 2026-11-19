"""Switches for pausing parts of the app quickly, e.g. during an incident or abuse.

Three switches, each on unless turned off:
- "signups": creating accounts
- "voice_checks": new passages and voice checks (paid speech-to-text)
- "enrollment": adding Voice ID samples (the model service)

Each lives in the `switches` collection, so anyone with database access can
flip one in seconds with scripts/switch.py, with no redeploy. The API re-reads
them at most every CACHE_SECONDS. A setting (SIGNUPS_ENABLED=false etc.) forces
one off regardless, as a backup for whoever runs the server.

If the collection can't be read, the last value seen is kept (or "on" if none
yet): with the database down, every route fails with 503 anyway, and a switch
staying on never skips any other check.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

import config
from db import get_switches_collection

logger = logging.getLogger("voiceguard.switches")

NAMES = ("signups", "voice_checks", "enrollment")
CACHE_SECONDS = 30

# What the people paused are told (the frontend words it itself, by name).
PAUSED_MESSAGES = {
    "signups": "Creating accounts is paused for now. Please try again later.",
    "voice_checks": "Voice checks are paused for now. Please try again later.",
    "enrollment": "Setting up a Voice ID is paused for now. Please try again later.",
}

# name -> (on, when it was read, by time.monotonic())
_cache: dict[str, tuple[bool, float]] = {}


class Paused(Exception):
    """A switch is off: answered with 503 and the switch's name."""

    def __init__(self, name: str):
        super().__init__(f"{name} is paused")
        self.name = name


def switches_store() -> Callable[[], Collection]:
    """The switches collection, fetched only when a value is due to be read
    (tests replace it)."""
    return get_switches_collection


def _forced_off(name: str) -> bool:
    return not {
        "signups": config.SIGNUPS_ENABLED,
        "voice_checks": config.VOICE_CHECKS_ENABLED,
        "enrollment": config.ENROLLMENT_ENABLED,
    }[name]


def is_on(name: str, store: Callable[[], Collection], now: float | None = None) -> bool:
    if _forced_off(name):
        return False
    now = time.monotonic() if now is None else now
    cached = _cache.get(name)
    if cached and now - cached[1] < CACHE_SECONDS:
        return cached[0]
    try:
        record = store().find_one({"_id": name})
        on = bool(record.get("on", True)) if record else True
    except (PyMongoError, config.NotConfigured) as exc:
        on = cached[0] if cached else True
        logger.warning("switch_unreadable name=%s reason=%s keeping=%s", name, type(exc).__name__, on)
    _cache[name] = (on, now)
    return on


def set_switch(store: Collection, name: str, on: bool, by: str, reason: str) -> None:
    """Flip a switch (used by scripts/switch.py). Keeps who, when and why."""
    if name not in NAMES:
        raise ValueError(f"Unknown switch: {name}. Choose from {', '.join(NAMES)}.")
    store.update_one(
        {"_id": name},
        {"$set": {"on": on, "changed_by": by, "changed_at": datetime.now(UTC), "reason": reason}},
        upsert=True,
    )


def require(name: str):
    """A route dependency: raise Paused unless the switch is on."""

    def check(store: Callable[[], Collection] = Depends(switches_store)) -> None:
        if not is_on(name, store):
            raise Paused(name)

    return check
