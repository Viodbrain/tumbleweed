"""Owner: B. Atlas lookups; distances are approximate straight-line miles."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.db import get_db
from app.models import FindFoodArgs, FoodEvent, GeoPoint, PlaceResult, ResolvedPoint

M_PER_MI = 1609.344


async def find_food(args: FindFoodArgs) -> list[PlaceResult]:
    if args.limit <= 0:
        return []
    if args.lat is not None or args.lng is not None:
        if args.lat is None or args.lng is None:
            return []
        if not math.isfinite(args.lat) or not math.isfinite(args.lng):
            return []
        if not (-90 <= args.lat <= 90 and -180 <= args.lng <= 180):
            return []
        origin = GeoPoint(coordinates=(args.lng, args.lat))
    else:
        resolved = await resolve_point(zip=args.zip, city=args.city)
        if resolved is None:
            return []
        origin = resolved.location
    query = {}
    for key, value in (("kind", args.kind), ("accepts_snap", args.accepts_snap), ("days", args.open_day)):
        if value is not None:
            query[key] = value
    cursor = await get_db().places.aggregate([
        {"$geoNear": {
            "near": origin.model_dump(), "key": "location", "distanceField": "distance_mi",
            "distanceMultiplier": 1 / M_PER_MI, "maxDistance": 40 * M_PER_MI,
            "spherical": True, "query": query,
        }},
        {"$limit": args.limit},
    ])
    return [PlaceResult.model_validate(row) async for row in cursor]


async def list_events(zip: str | None = None, city: str | None = None, days: int = 14) -> list[FoodEvent]:
    if type(days) is not int or days <= 0:
        return []
    now = datetime.now(UTC)
    try:
        end = now + timedelta(days=days)
    except OverflowError:
        return []
    resolved = await resolve_point(zip=zip, city=city)
    if resolved is None:
        return []
    cursor = await get_db().events.aggregate([
        {"$geoNear": {
            "near": resolved.location.model_dump(), "key": "location",
            "distanceField": "_distance_m", "maxDistance": 40 * M_PER_MI, "spherical": True,
            "query": {"starts_at": {"$gte": now, "$lte": end}},
        }},
        {"$sort": {"starts_at": 1, "_id": 1}},
        {"$limit": 5},
        {"$project": {"_distance_m": 0}},
    ])
    return [FoodEvent.model_validate(row) async for row in cursor]


async def resolve_point(zip: str | None = None, city: str | None = None) -> ResolvedPoint | None:
    if zip is not None:
        if not isinstance(zip, str) or len(zip.strip()) != 5 or not zip.strip().isdigit():
            return None
        query = {"_id": zip.strip()}
    elif isinstance(city, str) and city.strip():
        query = {"city": city.strip().lower()}
    else:
        return None
    row = await get_db().zips.find_one(query, sort=[("_id", 1)])
    if row is None:
        return None
    return ResolvedPoint(zip=row["_id"], location=GeoPoint.model_validate(row["location"]))
