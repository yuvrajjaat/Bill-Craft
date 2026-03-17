"""MongoDB connection singleton using pymongo."""
from pymongo import MongoClient
from django.conf import settings

_client = None
_db = None


def get_db():
    """Get MongoDB database instance (lazy singleton)."""
    global _client, _db
    if _db is None:
        _client = MongoClient(settings.MONGODB_URI)
        _db = _client.get_default_database()
    return _db


def get_collection(name):
    """Get a MongoDB collection by name."""
    return get_db()[name]
