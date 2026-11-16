"""Show or flip the pause switches (switches.py): signups, voice_checks, enrollment.

Usage, from backend/ with the virtual environment active:
    python scripts/switch.py status
    python scripts/switch.py signups off --by Gabriel --reason "signup flood"
    python scripts/switch.py signups on --by Gabriel --reason "flood over"

Uses MONGO_URI from the .env, so it changes whichever database that points at
(production for the team's .env). The API picks a change up within 30 seconds.
Never prints the database address.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo.collection import Collection

import config
from db import get_switches_collection
from switches import CACHE_SECONDS, NAMES, set_switch

SETTINGS = {"signups": "SIGNUPS_ENABLED", "voice_checks": "VOICE_CHECKS_ENABLED", "enrollment": "ENROLLMENT_ENABLED"}


def status_lines(store: Collection) -> list[str]:
    lines = []
    for name in NAMES:
        record = store.find_one({"_id": name}) or {}
        on = record.get("on", True)
        line = f"{name:<13} {'on ' if on else 'OFF'}"
        if record:
            line += f"  (set by {record.get('changed_by', '?')} at {record.get('changed_at', '?')}: {record.get('reason', '')})"
        if not getattr(config, SETTINGS[name]):
            line += f"  [forced off by {SETTINGS[name]}=false on this machine's settings]"
        lines.append(line)
    return lines


STRANDING_WARNING = (
    "WARNING: enrollment is off but signups is on. A new account can only set up its Voice ID "
    "within 30 minutes of signing up, so anyone who signs up now misses that window for good. "
    "Turn signups off too:  python scripts/switch.py signups off --by <name> --reason <why>"
)


def strands_new_accounts(store: Collection) -> bool:
    """True when sign-ups are on but enrollment is off."""

    def is_on(name: str) -> bool:
        return (store.find_one({"_id": name}) or {}).get("on", True)

    return is_on("signups") and not is_on("enrollment")


def main(argv: list[str] | None = None, store: Collection | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show or flip the VoiceGuard pause switches.")
    parser.add_argument("switch", choices=["status", *NAMES])
    parser.add_argument("state", nargs="?", choices=["on", "off"])
    parser.add_argument("--by", help="who is flipping it (kept on the switch)")
    parser.add_argument("--reason", help="why (kept on the switch)")
    args = parser.parse_args(argv)

    store = store if store is not None else get_switches_collection()
    if args.switch == "status":
        print("\n".join(status_lines(store)))
        if strands_new_accounts(store):
            print(STRANDING_WARNING, file=sys.stderr)
        return 0
    if args.state is None or not args.by or not args.reason:
        parser.error("flipping a switch needs on/off, --by and --reason")
    set_switch(store, args.switch, args.state == "on", by=args.by, reason=args.reason)
    print(f"{args.switch} is now {args.state.upper()}. The API picks this up within {CACHE_SECONDS} seconds.")
    if strands_new_accounts(store):
        print(STRANDING_WARNING, file=sys.stderr)
    print("\n".join(status_lines(store)))
    return 0


if __name__ == "__main__":
    from pymongo.errors import PyMongoError

    try:
        sys.exit(main())
    except config.NotConfigured as exc:
        sys.exit(f"Can't reach the database: {exc}")
    except PyMongoError as exc:
        sys.exit(f"Can't reach the database ({type(exc).__name__}). Check your connection and MONGO_URI.")
