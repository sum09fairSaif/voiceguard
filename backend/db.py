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
