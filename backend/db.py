from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

import config


@lru_cache
def get_client() -> MongoClient:
    if not config.MONGO_URI:
        raise RuntimeError("MONGO_URI is not set. Add it to your .env file.")
    # Give up after 5 seconds if the database can't be reached, instead of
    # leaving the user waiting for the default 30.
    return MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)


@lru_cache
def get_users_collection() -> Collection:
    users = get_client()[config.MONGO_DB_NAME]["users"]
    # The database itself refuses a second account with the same email,
    # even if two signups arrive at the same moment.
    users.create_index([("email", ASCENDING)], unique=True)
    return users


@lru_cache
def get_challenges_collection() -> Collection:
    challenges = get_client()[config.MONGO_DB_NAME]["challenges"]
    # MongoDB deletes each attempt by itself once its expiry time has passed.
    # Its clean-up only runs about once a minute, so the code still checks
    # the expiry time too.
    challenges.create_index("expires_at", expireAfterSeconds=0)
    # Speeds up finding a user's earlier passages to cancel them.
    challenges.create_index("user_id")
    return challenges


@lru_cache
def get_voiceprints_collection() -> Collection:
    # One encrypted voiceprint per user, keyed by user id.
    return get_client()[config.MONGO_DB_NAME]["voiceprints"]


@lru_cache
def get_rate_limits_collection() -> Collection:
    rate_limits = get_client()[config.MONGO_DB_NAME]["rate_limits"]
    # One counter per user per time window. MongoDB deletes each counter
    # once its window has ended.
    rate_limits.create_index("expires_at", expireAfterSeconds=0)
    return rate_limits


@lru_cache
def get_login_failures_collection() -> Collection:
    # Wrong-password counts and lockouts, one per email. MongoDB deletes
    # each once its window and any lockout have ended.
    login_failures = get_client()[config.MONGO_DB_NAME]["login_failures"]
    login_failures.create_index("expires_at", expireAfterSeconds=0)
    return login_failures


@lru_cache
def get_enrollments_collection() -> Collection:
    # Samples a user has given towards a voiceprint, keyed by user id.
    # MongoDB deletes an unfinished enrollment once it has expired.
    enrollments = get_client()[config.MONGO_DB_NAME]["enrollments"]
    enrollments.create_index("expires_at", expireAfterSeconds=0)
    return enrollments
