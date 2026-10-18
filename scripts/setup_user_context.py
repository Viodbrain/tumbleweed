"""Prepare persistent preferences: python -m scripts.setup_user_context --apply."""
# ruff: noqa: I001

import argparse
import asyncio

from pymongo.errors import CollectionInvalid

from scripts import _backend  # noqa: F401

from app.db import close_db, get_db


async def prepare(db):
    try:
        await db.create_collection("user_context")
    except CollectionInvalid:
        pass  # Already prepared, including a concurrent setup.
    indexes = await db.user_context.index_information()
    if indexes.get("_id_", {}).get("key") != [("_id", 1)]:
        raise RuntimeError("Expected the unique caller identity index")
    print("Ready: user_context with its unique _id index")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print("Create user_context if absent; keep existing data. Pass --apply to run.")
        return
    try:
        await prepare(get_db())
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
