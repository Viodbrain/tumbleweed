"""Shared, cached Atlas connection for the Python backend."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient


@lru_cache(maxsize=1)
def get_db():
    # Deployment environment takes precedence over local development settings.
    config = {**dotenv_values(Path(__file__).resolve().parents[1] / ".env.local"), **os.environ}
    uri = config.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
    return client[config.get("MONGODB_DB") or "tumbleweed"]
