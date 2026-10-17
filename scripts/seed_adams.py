"""Validate reviewed data; pass --apply to upsert it into Atlas."""
# ruff: noqa: I001

import argparse
import asyncio
import json
from pathlib import Path

from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from scripts import _backend  # noqa: F401

from app.db import close_db, get_db
from scripts.check_routing_data import valid_point
from scripts.setup_indexes import apply_indexes


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dataset", choices=["adams-wa", "ferry-wa"], default="adams-wa")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    datasets = {}
    for collection, filename in (("zips", "zips.json"), ("places", "places.json")):
        records = json.loads((root / "data" / args.dataset / filename).read_text())
        ids = set()
        for record in records:
            identifier = record.get("_id")
            if not isinstance(identifier, str) or not identifier or identifier in ids:
                raise ValueError(f"Invalid or duplicate ID in {filename}")
            ids.add(identifier)
            if not valid_point(record.get("location")):
                raise ValueError(f"Invalid location: {identifier}")
            if collection == "places":
                if not record.get("address") or type(record.get("accepts_snap")) is not bool:
                    raise ValueError(f"Incomplete place: {identifier}")
                if not isinstance(record.get("days"), list) or not set(record["days"]) <= {
                    "mon",
                    "tue",
                    "wed",
                    "thu",
                    "fri",
                    "sat",
                    "sun",
                }:
                    raise ValueError(f"Invalid open days: {identifier}")
            elif not (len(identifier) == 5 and identifier.isdigit() and record.get("city") and record.get("state")):
                raise ValueError(f"Incomplete ZIP: {identifier}")
        datasets[collection] = records
        print(f"Validated {len(records)} {collection} records.")
    if not args.apply:
        print("Dry run only. Pass --apply to load these records and create indexes.")
        return 0
    try:
        db = get_db()
        for collection, records in datasets.items():
            if records:
                result = await db[collection].bulk_write(
                    [
                        UpdateOne({"_id": r["_id"]}, {"$set": {k: v for k, v in r.items() if k != "_id"}}, upsert=True)
                        for r in records
                    ]
                )
                print(
                    f"{collection}: inserted {result.upserted_count}, matched {result.matched_count}, "
                    f"modified {result.modified_count}."
                )
        await apply_indexes(db)
        for collection, records in datasets.items():
            ids = [record["_id"] for record in records]
            if await db[collection].count_documents({"_id": {"$in": ids}}) != len(ids):
                raise ValueError(f"Not all seeded {collection} records were found.")
        # A county can span more than the search radius. Verify each ZIP's query
        # independently rather than requiring every place near the first ZIP.
        for zip_record in datasets["zips"]:
            cursor = await db.places.aggregate(
                [
                    {
                        "$geoNear": {
                            "near": zip_record["location"],
                            "key": "location",
                            "distanceField": "distance_m",
                            "maxDistance": 40 * 1609.344,
                            "spherical": True,
                        }
                    },
                ]
            )
            nearby = await cursor.to_list(length=None)
            print(f"ZIP {zip_record['_id']}: {len(nearby)} resources within 40 straight-line miles.")
        print("Atlas seed and nearby search verification succeeded.")
        return 0
    except (PyMongoError, RuntimeError) as exc:
        print(
            f"Atlas operation failed ({type(exc).__name__}). Credentials were not printed. "
            "Some writes may have completed; rerunning is safe."
        )
    finally:
        await close_db()
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
