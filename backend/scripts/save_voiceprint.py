"""Dev tool: save a voiceprint for an account from recordings on disk.

The app enrolls users through /api/enroll/samples. This script skips that
endpoint's quality checks and replaces any voiceprint the account already
has, so use it only on test accounts.

From backend/, with the venv active and .env filled in (MONGO_URI,
VOICEPRINT_KEY, EMBEDDING_SERVICE_URL, EMBEDDING_SERVICE_TOKEN):

    python scripts/save_voiceprint.py you@example.com take1.m4a take2.m4a take3.m4a

Each recording should be a few seconds of the account holder talking. The
recordings are sent to the model service and never stored.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_users_collection, get_voiceprints_collection  # noqa: E402
from embedding import get_embedder  # noqa: E402
from voiceprints import build_voiceprint, save_voiceprint  # noqa: E402


def main(email: str, paths: list[str]) -> None:
    embed = get_embedder()
    if embed is None:
        sys.exit("Set EMBEDDING_SERVICE_URL and EMBEDDING_SERVICE_TOKEN in .env first.")
    user = get_users_collection().find_one({"email": email.lower()})
    if user is None:
        sys.exit(f"No account with the email {email}.")

    embeddings = []
    for path in paths:
        with open(path, "rb") as file:
            embeddings.append(embed(file.read(), os.path.basename(path)).vector)
        print(f"Read {path}")

    save_voiceprint(get_voiceprints_collection(), str(user["_id"]), build_voiceprint(embeddings))
    print(f"Saved a voiceprint for {email} from {len(paths)} recording(s).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
