"""Validate reviewed data; pass --apply to upsert it into Atlas."""

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

from check_routing_data import valid_point


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    datasets = {}
    for collection, filename in (("zips", "zips.json"), ("places", "places.json")):
        records = json.loads((root / "data/adams-wa" / filename).read_text())
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
                if not isinstance(record.get("days"), list) or not set(record["days"]) <= {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
                    raise ValueError(f"Invalid open days: {identifier}")
            elif not (len(identifier) == 5 and identifier.isdigit() and record.get("city") and record.get("state")):
                raise ValueError(f"Incomplete ZIP: {identifier}")
        datasets[collection] = records
        print(f"Validated {len(records)} {collection} records.")
    if not args.apply:
        print("Dry run only. Pass --apply to load these records and create indexes.")
        return 0
    config = dotenv_values(root / ".env.local")
    uri = config.get("MONGODB_URI")
    if not uri:
        print("Missing MONGODB_URI in .env.local")
        return 1
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000) as client:
            db = client[config.get("MONGODB_DB") or "tumbleweed"]
            for collection, records in datasets.items():
                if records:
                    result = db[collection].bulk_write([
                        UpdateOne({"_id": r["_id"]}, {"$set": {k: v for k, v in r.items() if k != "_id"}}, upsert=True)
                        for r in records
                    ])
                    print(f"{collection}: inserted {result.upserted_count}, matched {result.matched_count}, modified {result.modified_count}.")
            db.places.create_index([("location", "2dsphere")])
            db.places.create_index("region")
            db.zips.create_index([("location", "2dsphere")])
            db.zips.create_index("city")
            origin = db.zips.find_one({"_id": "99344"})["location"]
            nearby = list(db.places.aggregate([
                {"$geoNear": {"near": origin, "key": "location", "distanceField": "distance_m", "maxDistance": 40 * 1609.344, "spherical": True, "query": {"_id": {"$in": [r["_id"] for r in datasets["places"]]}, "accepts_snap": True}}},
                {"$limit": 3},
            ]))
            if len(nearby) != len(datasets["places"]):
                raise ValueError("Nearby lookup did not return all seeded places.")
            for place in nearby:
                print(f"Verified nearby: {place['name']} ({place['distance_m'] / 1609.344:.2f} straight-line miles)")
            print("Atlas seed and nearby search verification succeeded.")
        return 0
    except PyMongoError as exc:
        print(f"Atlas operation failed ({type(exc).__name__}). Credentials were not printed. Some writes may have completed; rerunning is safe.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
