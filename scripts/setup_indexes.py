"""Create agreed indexes; run as python -m scripts.setup_indexes --apply."""
# ruff: noqa: I001

import argparse
import asyncio

from pymongo.errors import PyMongoError

from scripts import _backend  # noqa: F401

from app.db import close_db, get_db

INDEXES = {
    "places": [([("location", "2dsphere")], {}), ([("region", 1)], {})],
    "events": [([("location", "2dsphere")], {}), ([("starts_at", 1)], {})],
    "zips": [([("city", 1)], {}), ([("location", "2dsphere")], {})],
    "users": [([("handle", 1)], {"unique": True})],
    "messages": [([("handle", 1), ("created_at", -1)], {}), ([("created_at", -1)], {})],
    # _id is already unique and is the webhook message deduplication key.
    "webhook_events": [([("received_at", 1)], {})],
}


async def apply_indexes(db):
    for collection, indexes in INDEXES.items():
        for keys, options in indexes:
            name = await db[collection].create_index(keys, **options)
            print(f"Ready: {collection}.{name}")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        for collection, indexes in INDEXES.items():
            print(f"{collection}: {indexes}")
        print("Dry run. Pass --apply to create indexes.")
        return 0
    try:
        await apply_indexes(get_db())
        return 0
    except (PyMongoError, RuntimeError):
        print("Index setup failed. Check configuration, permissions, and existing duplicate handles.")
        return 1
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
