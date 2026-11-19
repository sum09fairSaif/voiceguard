"""What makes a password acceptable when one is set (NIST SP 800-63B-4).

At least 15 characters (the minimum length is in schemas.SignupRequest), no
composition rules, and the whole password must not be a known-bad one:
common or breached, the person's own context (their email's name, the app's
name), one short chunk repeated, or a sequential or keyboard run. Only the
whole password is compared: one that merely contains a common word is fine.
"""

import re
from functools import lru_cache
from pathlib import Path

MIN_LENGTH = 15

_LIST = Path(__file__).parent / "data" / "common-passwords-15plus.txt"
_APP_WORDS = ("voiceguard", "voice guard")
# Runs people type: the alphabet, digits and keyboard rows, either way round.
_RUNS = ("abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiopasdfghjklzxcvbnm", "1qaz2wsx3edc4rfv5tgb6yhn7ujm")


@lru_cache
def _common() -> frozenset[str]:
    """The bundled list, read once per process (see data/README.md)."""
    with _LIST.open(encoding="utf-8") as lines:
        return frozenset(line.rstrip("\n") for line in lines if line.strip())


def _letters_and_digits(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_repeated(text: str) -> bool:
    # One chunk, shorter than the whole, repeated: "aaaa…", "abcabc…",
    # "passwordpassword".
    return re.fullmatch(r"(.+?)\1+", text, flags=re.DOTALL) is not None


def _is_run(text: str) -> bool:
    for run in _RUNS:
        wrapped = run * 8
        if text in wrapped or text in wrapped[::-1]:
            return True
    return False


def _context_words(email: str) -> list[str]:
    name = email.split("@", 1)[0]
    words = [_letters_and_digits(word) for word in (name, *_APP_WORDS)]
    return [word for word in words if len(word) >= 3]


def password_problem(password: str, email: str = "") -> str | None:
    """None if the password is acceptable, otherwise why not: "common",
    "personal", "repetitive" or "sequential". The minimum length is checked
    separately."""
    lowered = password.lower()
    if lowered.strip() in _common():
        return "common"

    core = _letters_and_digits(password)
    # The app's or the person's own name, with trimmings: "VoiceGuard2026!!",
    # "sam.doe-sam.doe", "samdoe1234567890".
    letters = re.sub(r"[0-9]", "", core)
    for word in _context_words(email):
        word_letters = re.sub(r"[0-9]", "", word)
        if core == word or (word_letters and (letters == word_letters or _is_whole_repeat(letters, word_letters))):
            return "personal"

    if _is_repeated(lowered) or (core and _is_repeated(core)):
        return "repetitive"
    if core and len(core) >= len(password) // 2 and _is_run(core):
        return "sequential"
    return None


def _is_whole_repeat(text: str, unit: str) -> bool:
    return bool(text) and len(text) % len(unit) == 0 and text == unit * (len(text) // len(unit))
