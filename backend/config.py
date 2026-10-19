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
# Optional Hugging Face access token. The model service runs on ZeroGPU,
# which rations GPU time per caller; with this set, the backend's calls
# count against that account instead of as anonymous use. Without it (or
# once the quota is used up) the service falls back to its CPU.
EMBEDDING_SERVICE_HF_TOKEN = os.getenv("EMBEDDING_SERVICE_HF_TOKEN", "")
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

# Enrollment. Provisional limits: set them from the evaluation harness and
# the per-sample log lines once there are real recordings.
# How many good samples make a voiceprint.
ENROLL_SAMPLES_REQUIRED = int(os.getenv("ENROLL_SAMPLES_REQUIRED", "3"))
# Least voice (not silence) a sample must hold. Reading a six-word passage
# gives about 2 seconds.
ENROLL_MIN_SPEECH_SECONDS = float(os.getenv("ENROLL_MIN_SPEECH_SECONDS", "1.5"))
# Most of a sample that may be cut off at full volume (0.01 = 1%).
ENROLL_MAX_CLIPPED_SHARE = float(os.getenv("ENROLL_MAX_CLIPPED_SHARE", "0.01"))
# Lowest similarity between a new sample and the user's earlier ones. Below
# it, the sample is probably noise, another voice, or a bad microphone.
ENROLL_CONSISTENCY_THRESHOLD = float(os.getenv("ENROLL_CONSISTENCY_THRESHOLD", "0.5"))
# How long accepted samples wait for the rest before they're thrown away.
ENROLL_SESSION_TTL_SECONDS = int(os.getenv("ENROLL_SESSION_TTL_SECONDS", "1800"))
# Each sample is a model-service call. A user who has to redo every take
# still stays well under this.
ENROLL_RATE_LIMIT = int(os.getenv("ENROLL_RATE_LIMIT", "20"))
if ENROLL_SAMPLES_REQUIRED <= 0 or ENROLL_SESSION_TTL_SECONDS <= 0 or ENROLL_RATE_LIMIT <= 0:
    raise RuntimeError("ENROLL_SAMPLES_REQUIRED, ENROLL_SESSION_TTL_SECONDS and ENROLL_RATE_LIMIT must be more than 0.")
if ENROLL_MIN_SPEECH_SECONDS < 0 or not 0.0 <= ENROLL_MAX_CLIPPED_SHARE <= 1.0:
    raise RuntimeError("ENROLL_MIN_SPEECH_SECONDS can't be negative; ENROLL_MAX_CLIPPED_SHARE must be between 0 and 1.")
if not -1.0 <= ENROLL_CONSISTENCY_THRESHOLD <= 1.0:
    raise RuntimeError("ENROLL_CONSISTENCY_THRESHOLD must be between -1 and 1.")
