import os

from dotenv import load_dotenv

# Read the local .env file (if there is one) into environment variables.
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "voiceguard")

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
if JWT_EXPIRE_MINUTES <= 0:
    raise RuntimeError("JWT_EXPIRE_MINUTES must be more than 0.")

CHALLENGE_TTL_SECONDS = int(os.getenv("CHALLENGE_TTL_SECONDS", "120"))
if CHALLENGE_TTL_SECONDS <= 0:
    raise RuntimeError("CHALLENGE_TTL_SECONDS must be more than 0.")

# Hosted speech-to-text. Left blank, voice checks answer "unavailable"
# instead of crashing.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

# Content check limits. Provisional: tune them with real recordings.
# How many passage words may be misheard or missing and still pass.
CONTENT_MAX_MISSED_WORDS = int(os.getenv("CONTENT_MAX_MISSED_WORDS", "1"))
# How many words that aren't in the passage ("um, okay") may be heard and
# still pass. Beyond this, a long recording that happens to contain the
# passage fails.
CONTENT_MAX_EXTRA_WORDS = int(os.getenv("CONTENT_MAX_EXTRA_WORDS", "4"))
if CONTENT_MAX_MISSED_WORDS < 0 or CONTENT_MAX_EXTRA_WORDS < 0:
    raise RuntimeError("CONTENT_MAX_MISSED_WORDS and CONTENT_MAX_EXTRA_WORDS can't be negative.")

# Identity check. The model service turns a recording into a voice
# embedding (see model-service/). Left blank, users with a voiceprint get
# "unavailable"; users without one are unaffected.
EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL", "")
EMBEDDING_SERVICE_TOKEN = os.getenv("EMBEDDING_SERVICE_TOKEN", "")
# Which model made the voiceprints. Changing models means re-enrolling.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
# Encrypts voiceprints at rest. A Fernet key: generate one with
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
VOICEPRINT_KEY = os.getenv("VOICEPRINT_KEY", "")
# Lowest cosine similarity that counts as the same speaker. Provisional:
# SpeechBrain's own default (0.25) let two different synthetic voices pass
# as each other on six-word clips (they scored 0.33 and 0.42; the same
# voice scored 0.80 to 0.87). Set it from the evaluation harness with real
# recordings before relying on it.
IDENTITY_THRESHOLD = float(os.getenv("IDENTITY_THRESHOLD", "0.5"))
if not -1.0 <= IDENTITY_THRESHOLD <= 1.0:
    raise RuntimeError("IDENTITY_THRESHOLD must be between -1 and 1.")

# Per-user limits. Each voice check is a paid speech-to-text call, so these
# cap what one account can spend. After 3 failed voice attempts the user
# falls back to an email code, so a real user stays well under them.
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "3600"))
CHALLENGE_RATE_LIMIT = int(os.getenv("CHALLENGE_RATE_LIMIT", "20"))
VERIFY_RATE_LIMIT = int(os.getenv("VERIFY_RATE_LIMIT", "10"))
if RATE_LIMIT_WINDOW_SECONDS <= 0 or CHALLENGE_RATE_LIMIT <= 0 or VERIFY_RATE_LIMIT <= 0:
    raise RuntimeError("RATE_LIMIT_WINDOW_SECONDS, CHALLENGE_RATE_LIMIT and VERIFY_RATE_LIMIT must be more than 0.")
