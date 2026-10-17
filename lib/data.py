"""Food searches using approximate straight-line distances, in miles."""

import math
from datetime import datetime, timedelta, timezone

from .db import get_db

M_PER_MI = 1609.344
DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
KINDS = {"foodbank", "grocery", "market", "meal"}


def resolve_point(*, zip=None, city=None):
    """Resolve a known ZIP or exact town name. Unknown/bad inputs return None."""
    if zip is not None:
        if not isinstance(zip, str) or len(zip.strip()) != 5 or not zip.strip().isdigit():
            return None
        query = {"_id": zip.strip()}
    elif isinstance(city, str) and city.strip():
        query = {"city": city.strip().lower()}
    else:
        return None
    row = get_db().zips.find_one(query, sort=[("_id", 1)])
    return {"zip": row["_id"], "location": row["location"]} if row else None


def find_food(*, zip=None, city=None, lat=None, lng=None, kind=None,
              accepts_snap=None, open_day=None, limit=3):
    """Return up to limit places within 40 miles, nearest first.

    Unknown open days are excluded when filtering by day. This does not check
    current time, holidays, road accessibility, or driving distances. Database
    failures propagate so the brain can distinguish an outage from no matches.
    """
    if type(limit) is not int or limit <= 0:
        return []
    if kind is not None and (not isinstance(kind, str) or kind not in KINDS):
        return []
    if open_day is not None and (not isinstance(open_day, str) or open_day not in DAYS):
        return []
    if accepts_snap is not None and type(accepts_snap) is not bool:
        return []
    if lat is not None or lng is not None:
        if not all(type(n) in (int, float) and math.isfinite(n) for n in (lat, lng)):
            return []
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return []
        origin = {"type": "Point", "coordinates": [lng, lat]}
    else:
        resolved = resolve_point(zip=zip, city=city)
        if resolved is None:
            return []
        origin = resolved["location"]
    filters = {}
    for key, value in (("kind", kind), ("accepts_snap", accepts_snap), ("days", open_day)):
        if value is not None:
            filters[key] = value
    return list(get_db().places.aggregate([
        {"$geoNear": {"near": origin, "key": "location", "distanceField": "distance_mi",
                      "distanceMultiplier": 1 / M_PER_MI, "maxDistance": 40 * M_PER_MI,
                      "spherical": True, "query": filters}},
        {"$limit": limit},
    ]))


def list_events(*, zip=None, city=None, days=14):
    """Return at most five nearby future events, soonest first.

    Events use the shared FoodEvent shape with ISO 8601 starts_at strings.
    Invalid dates are excluded. The window runs from now through `days` days
    ahead, and the search radius is 40 straight-line miles.
    """
    if type(days) is not int or days <= 0:
        return []
    now = datetime.now(timezone.utc)
    try:
        end = now + timedelta(days=days)
    except OverflowError:
        return []
    resolved = resolve_point(zip=zip, city=city)
    if resolved is None:
        return []
    return list(get_db().events.aggregate([
        {"$geoNear": {"near": resolved["location"], "key": "location",
                      "distanceField": "_distance_m", "maxDistance": 40 * M_PER_MI,
                      "spherical": True}},
        {"$set": {"_starts_at": {"$convert": {"input": "$starts_at", "to": "date",
                                              "onError": None, "onNull": None}}}},
        {"$match": {"_starts_at": {"$gte": now, "$lte": end}}},
        {"$sort": {"_starts_at": 1, "_id": 1}},
        {"$limit": 5},
        {"$project": {"_distance_m": 0, "_starts_at": 0}},
    ]))
