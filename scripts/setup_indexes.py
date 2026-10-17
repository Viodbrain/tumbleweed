"""Create the agreed data-layer indexes; dry run unless --apply is supplied."""

import argparse

from pymongo.errors import PyMongoError

from lib.db import get_db

INDEXES = {
    "places": [[("location", "2dsphere")], [("region", 1)]],
    "events": [[("location", "2dsphere")], [("starts_at", 1)]],
    "zips": [[("city", 1)], [("location", "2dsphere")]],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        for collection, indexes in INDEXES.items():
            print(f"{collection}: {indexes}")
        print("Dry run. Pass --apply to create indexes.")
        return 0
    try:
        db = get_db()
        for collection, indexes in INDEXES.items():
            for keys in indexes:
                name = db[collection].create_index(keys)
                print(f"Ready: {collection}.{name}")
        return 0
    except (PyMongoError, RuntimeError):
        print("Index setup failed. Check database configuration and permissions.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
