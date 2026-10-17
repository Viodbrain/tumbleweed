"""Owner: B. Shared async MongoDB handle."""

from __future__ import annotations

import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

_client: AsyncMongoClient | None = None


def get_db() -> AsyncDatabase:
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _client = AsyncMongoClient(uri, tz_aware=True)
    return _client[os.getenv("MONGODB_DB", "tumbleweed")]
