"""Owner: B. Shared async MongoDB handle."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

_client: AsyncMongoClient | None = None


def get_db() -> AsyncDatabase:
    global _client
    backend = Path(__file__).resolve().parents[1]
    config = {
        **dotenv_values(backend.parent / ".env.local"),
        **dotenv_values(backend / ".env"),
        **dotenv_values(backend / ".env.local"),
        **os.environ,
    }
    if _client is None:
        uri = config.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _client = AsyncMongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
    return _client[config.get("MONGODB_DB") or "tumbleweed"]
