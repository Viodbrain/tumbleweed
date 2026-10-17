"""Run from the repository root: python -m scripts.find_food --zip 99344."""
# ruff: noqa: I001

import argparse
import asyncio
import sys

from pymongo.errors import PyMongoError

from scripts import _backend  # noqa: F401

from app.data import find_food
from app.db import close_db
from app.models import FindFoodArgs


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--zip")
    origin.add_argument("--city")
    parser.add_argument("--snap", action="store_true")
    parser.add_argument("--day", choices=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    args = parser.parse_args()
    try:
        places = await find_food(
            FindFoodArgs(zip=args.zip, city=args.city, accepts_snap=True if args.snap else None, open_day=args.day)
        )
    except (PyMongoError, RuntimeError):
        print("Database lookup failed. Check credentials, network access, and Atlas availability.")
        return 1
    finally:
        await close_db()
    if not places:
        print("No matching places found; check location coverage and filters.")
    for place in places:
        print(f"{place.name} — approx. {place.distance_mi:.2f} straight-line miles")
        print(f"  Address: {place.address}")
        print(f"  Hours: {place.hours or 'Unknown'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
