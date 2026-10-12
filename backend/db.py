from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

import config


@lru_cache
def get_client() -> MongoClient:
    if not config.MONGO_URI:
        raise RuntimeError("MONGO_URI is not set. Add it to your .env file.")
    return MongoClient(config.MONGO_URI)


@lru_cache
def get_users_collection() -> Collection:
    users = get_client()[config.MONGO_DB_NAME]["users"]
    # The database itself refuses a second account with the same email,
    # even if two signups arrive at the same moment.
    users.create_index([("email", ASCENDING)], unique=True)
    return users
