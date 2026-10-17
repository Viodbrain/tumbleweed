"""Run from the repo root: python -m scripts.list_events --zip 99344."""
# ruff: noqa: I001

import argparse
import asyncio

from pymongo.errors import PyMongoError

from scripts import _backend  # noqa: F401

from app.data import list_events
from app.db import close_db


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--zip")
    origin.add_argument("--city")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be positive")
    try:
        events = await list_events(zip=args.zip, city=args.city, days=args.days)
    except (PyMongoError, RuntimeError):
        print("Event lookup failed. Check database connectivity and event indexes.")
        return 1
    finally:
        await close_db()
    if not events:
        print("No upcoming events found for this location and time window.")
    for event in events:
        print(f"{event.title} at {event.place_name}")
        print(f"  Address: {event.address}")
        print(f"  Starts: {event.starts_at}")
        if event.notes:
            print(f"  Notes: {event.notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
