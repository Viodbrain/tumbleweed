"""Run from the repo root: python -m scripts.list_events --zip 99344."""

import argparse

from pymongo.errors import PyMongoError

from lib.data import list_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--zip")
    origin.add_argument("--city")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be positive")
    try:
        events = list_events(zip=args.zip, city=args.city, days=args.days)
    except (PyMongoError, RuntimeError):
        print("Event lookup failed. Check database connectivity and event indexes.")
        return 1
    if not events:
        print("No upcoming events found for this location and time window.")
    for event in events:
        print(f"{event['title']} at {event['place_name']}")
        print(f"  Address: {event['address']}")
        print(f"  Starts: {event['starts_at']}")
        if event.get("notes"):
            print(f"  Notes: {event['notes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
