"""Read-only Atlas check: python -m scripts.test_mongodb."""
# ruff: noqa: I001

import asyncio

from pymongo.errors import OperationFailure, PyMongoError

from scripts import _backend  # noqa: F401

from app.db import close_db, get_db


async def main():
    try:
        db = get_db()
        await db.client.admin.command("ping")
        collections = await db.list_collection_names()
        print("Atlas connection and authentication succeeded.")
        print(f"Database: {db.name}; visible collections: {len(collections)}")
        return 0
    except OperationFailure as exc:
        print(f"Atlas rejected the operation (code {exc.code}). Check credentials and permissions.")
    except (PyMongoError, RuntimeError, ValueError):
        print("Connection failed. Check backend/.env, the Atlas IP access list, and network access.")
    finally:
        await close_db()
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
