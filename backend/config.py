import math
import os
from datetime import UTC, datetime

from dotenv import load_dotenv

# Read the local .env file (if there is one) into environment variables.
load_dotenv()


class NotConfigured(RuntimeError):
    """A setting the server needs (e.g. MONGO_URI) is missing. Answered
    with a 503 rather than a crash; the log names the missing setting."""


MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "voiceguard")

# Websites allowed to call this API from a browser (CORS), comma-separated.
# The default covers local development and the live frontend.
ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,https://voiceguard-nu.vercel.app").split(",")
    if origin.strip()
]
# Also allowed: Vercel's preview deployments of the frontend (one per
# branch and commit), whose addresses all end in our Vercel team's name.
# Set to empty to turn off. Sign-in tokens travel in a header, not a
# cookie, so CORS is a second line of defence here, not the only one.
ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://voiceguard-[a-z0-9-]+-voice-guard2\.vercel\.app") or None

def is_true(value: str) -> bool:
    """Only the word "true" (any case, spaces ignored) turns a switch on."""
    return value.strip().lower() == "true"


# The interactive API docs (/docs, /redoc, /openapi.json). Handy locally,
# but in production they'd hand anyone a map of every route, so off unless
# set to true.
DOCS_ENABLED = is_true(os.getenv("DOCS_ENABLED", ""))

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
# Who issues our tokens and who they're for: a token minted for anything
# else (or before these were added) is refused.
JWT_ISSUER = "voiceguard-api"
JWT_AUDIENCE = "voiceguard-app"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
if JWT_EXPIRE_MINUTES <= 0:
    raise RuntimeError("JWT_EXPIRE_MINUTES must be more than 0.")
# A voice-verified token (password and an approved voice check) is the only
# one that opens the account, so it's kept short.
VERIFIED_TOKEN_MINUTES = int(os.getenv("VERIFIED_TOKEN_MINUTES", "15"))
if VERIFIED_TOKEN_MINUTES <= 0:
    raise RuntimeError("VERIFIED_TOKEN_MINUTES must be more than 0.")

# Sign-in lockout: this many wrong passwords for one email within the
# window locks that email out for the lockout time.
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("LOGIN_FAILURE_WINDOW_SECONDS", "900"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "1800"))
if LOGIN_MAX_FAILURES <= 0 or LOGIN_FAILURE_WINDOW_SECONDS <= 0 or LOGIN_LOCKOUT_SECONDS <= 0:
    raise RuntimeError("LOGIN_MAX_FAILURES, LOGIN_FAILURE_WINDOW_SECONDS and LOGIN_LOCKOUT_SECONDS must be more than 0.")

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
# Email (email_sender.py), through Resend's HTTP API: Render's free plan
# blocks SMTP. EMAIL_FROM is e.g. "VoiceGuard <noreply@send.example.com>" on
# a domain verified in Resend; until there is one, only
# "onboarding@resend.dev", which Resend delivers only to the Resend
# account's own address. Left blank, sending answers 503; nothing else is
# affected.
EMAIL_API_KEY = os.getenv("EMAIL_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
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
# Liveness check, run by the same model service. Lowest liveness score that
# counts as a live person; recordings below it are rejected even when the
# voice matches. The score is the model's raw "real" output, not a
# probability, and belongs to one model (the service reports which):
# retraining means choosing it again. LIVENESS_THRESHOLD_PLACEHOLDER
LIVENESS_THRESHOLD = float(os.getenv("LIVENESS_THRESHOLD", "0.0"))
if not math.isfinite(LIVENESS_THRESHOLD):
    raise RuntimeError("LIVENESS_THRESHOLD must be a number.")

# Whether a voice check's answer says which check (words, voice, liveness)
# passed or failed (#112). Off by default: knowing which check failed helps
# someone tune a replay or voice clone. Off, the answer has only the outcome,
# a general reason and the attempts left; the server log keeps the details.
# Set to true only for demos or debugging, never on the live server.
VERIFY_CHECK_DETAILS = os.getenv("VERIFY_CHECK_DETAILS", "false").strip().lower() in ("1", "true", "yes")

# Failed voice checks. After this many rejections within the window, voice
# checks are locked for the lockout time, and the user falls back to an
# email code (#20). Only rejections count, not outages or unenrolled users.
VOICE_MAX_FAILURES = int(os.getenv("VOICE_MAX_FAILURES", "3"))
VOICE_FAILURE_WINDOW_SECONDS = int(os.getenv("VOICE_FAILURE_WINDOW_SECONDS", "1800"))
VOICE_LOCKOUT_SECONDS = int(os.getenv("VOICE_LOCKOUT_SECONDS", "1800"))
if VOICE_MAX_FAILURES <= 0 or VOICE_FAILURE_WINDOW_SECONDS <= 0 or VOICE_LOCKOUT_SECONDS <= 0:
    raise RuntimeError("VOICE_MAX_FAILURES, VOICE_FAILURE_WINDOW_SECONDS and VOICE_LOCKOUT_SECONDS must be more than 0.")

# Per-user limits. Each voice check is a paid speech-to-text call, so these
# cap what one account can spend. After 3 failed voice attempts the user
# falls back to an email code, so a real user stays well under them.
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "3600"))
CHALLENGE_RATE_LIMIT = int(os.getenv("CHALLENGE_RATE_LIMIT", "20"))
VERIFY_RATE_LIMIT = int(os.getenv("VERIFY_RATE_LIMIT", "10"))
# New accounts per window, from everyone together. Each account gets its
# own voice-check allowance above, so without this one person could open
# many accounts to multiply the paid calls. Counted across everyone, not
# per address: behind Render's proxy the caller's address is either the
# proxy's or taken from a header that can be faked.
SIGNUP_RATE_LIMIT = int(os.getenv("SIGNUP_RATE_LIMIT", "30"))
if RATE_LIMIT_WINDOW_SECONDS <= 0 or CHALLENGE_RATE_LIMIT <= 0 or VERIFY_RATE_LIMIT <= 0 or SIGNUP_RATE_LIMIT <= 0:
    raise RuntimeError(
        "RATE_LIMIT_WINDOW_SECONDS, CHALLENGE_RATE_LIMIT, VERIFY_RATE_LIMIT and SIGNUP_RATE_LIMIT must be more than 0."
    )

# Enrollment. Provisional limits: set them from the evaluation harness and
# the per-sample log lines once there are real recordings.
# How many good samples make a voiceprint.
ENROLL_SAMPLES_REQUIRED = int(os.getenv("ENROLL_SAMPLES_REQUIRED", "3"))
# Least voice (not silence) a sample must hold. Only 30 ms slices above
# about -40 dBFS count, so pauses and quiet sounds don't: 300 Common Voice
# read sentences (about 4 s each) gave a median of 2.1 s, and a quarter
# under 1.4 s. Raising this would turn away many genuine reads; the words
# are what show the whole sentence was read.
ENROLL_MIN_SPEECH_SECONDS = float(os.getenv("ENROLL_MIN_SPEECH_SECONDS", "1.5"))
# Most of a sample that may be cut off at full volume (0.01 = 1%).
ENROLL_MAX_CLIPPED_SHARE = float(os.getenv("ENROLL_MAX_CLIPPED_SHARE", "0.01"))
# Lowest similarity between a new sample and each of the user's earlier
# ones (every one, not just their average). Below it, the sample is
# probably noise, another voice, or a bad microphone. Set above
# IDENTITY_THRESHOLD: samples recorded minutes apart in one place should
# be closer to each other than a later voice check is to the voiceprint.
ENROLL_CONSISTENCY_THRESHOLD = float(os.getenv("ENROLL_CONSISTENCY_THRESHOLD", "0.6"))
# Words heard beyond the sentence that a sample may still have (a stumble,
# a repeated word). Every word of the sentence must be there regardless.
ENROLL_MAX_EXTRA_WORDS = int(os.getenv("ENROLL_MAX_EXTRA_WORDS", "2"))
# Sentences handed out for enrollment are remembered so a sample can be
# checked against them. Only each user's newest few are kept, since the
# screen can ask for a new one at any time.
ENROLL_PROMPTS_KEPT = int(os.getenv("ENROLL_PROMPTS_KEPT", "5"))
# How long accepted samples wait for the rest before they're thrown away.
ENROLL_SESSION_TTL_SECONDS = int(os.getenv("ENROLL_SESSION_TTL_SECONDS", "1800"))
# Each sample is a model-service call. A user who has to redo every take
# still stays well under this.
ENROLL_RATE_LIMIT = int(os.getenv("ENROLL_RATE_LIMIT", "20"))
# Enrollment only in the signup session: with the signup token, this long
# after the account was created (see enrollment_window.py).
ENROLL_WINDOW_MINUTES = int(os.getenv("ENROLL_WINDOW_MINUTES", "30"))
if ENROLL_WINDOW_MINUTES <= 0:
    raise RuntimeError("ENROLL_WINDOW_MINUTES must be more than 0.")


def grace_until(value: str):
    """The one-off grace period's end (ISO 8601, UTC if no zone given), or
    None when empty (no grace period)."""
    value = value.strip()
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# Accounts created before this moment that never enrolled may enroll after
# signing in, until it. Default: the start of the security test week
# (Monday 2026-11-16 00:00 US Eastern).
ENROLL_GRACE_UNTIL = grace_until(os.getenv("ENROLL_GRACE_UNTIL", "2026-11-16T05:00:00Z"))
if ENROLL_SAMPLES_REQUIRED <= 0 or ENROLL_SESSION_TTL_SECONDS <= 0 or ENROLL_RATE_LIMIT <= 0:
    raise RuntimeError("ENROLL_SAMPLES_REQUIRED, ENROLL_SESSION_TTL_SECONDS and ENROLL_RATE_LIMIT must be more than 0.")
if ENROLL_MIN_SPEECH_SECONDS < 0 or not 0.0 <= ENROLL_MAX_CLIPPED_SHARE <= 1.0:
    raise RuntimeError("ENROLL_MIN_SPEECH_SECONDS can't be negative; ENROLL_MAX_CLIPPED_SHARE must be between 0 and 1.")
if not -1.0 <= ENROLL_CONSISTENCY_THRESHOLD <= 1.0:
    raise RuntimeError("ENROLL_CONSISTENCY_THRESHOLD must be between -1 and 1.")
if ENROLL_MAX_EXTRA_WORDS < 0 or ENROLL_PROMPTS_KEPT <= 0:
    raise RuntimeError("ENROLL_MAX_EXTRA_WORDS can't be negative; ENROLL_PROMPTS_KEPT must be more than 0.")
