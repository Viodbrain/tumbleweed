"""Check Atlas connectivity without printing credentials or changing data."""

import sys
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError


def main():
    config = dotenv_values(Path(__file__).resolve().parents[1] / ".env.local")
    uri = config.get("MONGODB_URI")
    if not uri:
        print("Missing MONGODB_URI in .env.local")
        return 1
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000) as client:
            client.admin.command("ping")
            database = config.get("MONGODB_DB") or "tumbleweed"
            collections = client[database].list_collection_names()
            print("Atlas connection and authentication succeeded.")
            print(f"Database: {database}; visible collections: {len(collections)}")
            if not config.get("MONGODB_DB"):
                print("MONGODB_DB is missing; used default tumbleweed. Add MONGODB_DB=tumbleweed to .env.local.")
        return 0
    except OperationFailure as exc:
        print(f"Atlas rejected the operation (code {exc.code}). Check database credentials and permissions.")
    except (PyMongoError, ValueError):
        print("Connection failed. Check the URI, Atlas IP access list, cluster status, and network access.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
