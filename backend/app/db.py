"""Owner: B. Shared async MongoDB handle."""

from __future__ import annotations

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import get_config

_client: AsyncMongoClient | None = None
_database_name: str | None = None


def get_db() -> AsyncDatabase:
    global _client, _database_name
    if _client is None:
        config = get_config()
        uri = config.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _client = AsyncMongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
        _database_name = config.get("MONGODB_DB") or "tumbleweed"
    return _client[_database_name]


async def close_db() -> None:
    global _client, _database_name
    if _client is not None:
        await _client.close()
        _client = None
        _database_name = None
