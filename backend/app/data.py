"""Owner: B. STUB -- replace the bodies, never the signatures."""

from __future__ import annotations

from app.models import FindFoodArgs, FoodEvent, GeoPoint, PlaceResult, ResolvedPoint

_FAKE = [
    PlaceResult(_id="stub-1", name="Stub Food Bank", kind="foodbank", address="1 Main St",
                location=GeoPoint(coordinates=(-122.33, 47.61)), hours="Tue/Thu 10am-2pm",
                days=["tue", "thu"], accepts_snap=False, phone="555-0100", notes="No ID required",
                region="seattle", distance_mi=0.8),
    PlaceResult(_id="stub-2", name="Stub Grocery", kind="grocery", address="2 Main St",
                location=GeoPoint(coordinates=(-122.34, 47.62)), hours="Daily 7am-10pm",
                days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"], accepts_snap=True,
                region="seattle", distance_mi=1.4),
    PlaceResult(_id="stub-3", name="Stub Farmers Market", kind="market", address="3 Main St",
                location=GeoPoint(coordinates=(-122.35, 47.63)), hours="Sat 9am-2pm", days=["sat"],
                accepts_snap=True, notes="Market Match doubles SNAP", region="seattle", distance_mi=2.2),
]


async def find_food(args: FindFoodArgs) -> list[PlaceResult]:
    return _FAKE[: args.limit]


async def list_events(zip: str | None = None, city: str | None = None, days: int = 14) -> list[FoodEvent]:
    return []


async def resolve_point(zip: str | None = None, city: str | None = None) -> ResolvedPoint | None:
    return ResolvedPoint(zip=zip, location=GeoPoint(coordinates=(-122.33, 47.61)))
