"""Validate local destination addresses and GeoJSON points before routing."""

import json
import math
from pathlib import Path


def valid_point(point):
    if not isinstance(point, dict) or point.get("type") != "Point":
        return False
    coordinates = point.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) != 2:
        return False
    if not all(type(n) in (int, float) and math.isfinite(n) for n in coordinates):
        return False
    lng, lat = coordinates
    return -180 <= lng <= 180 and -90 <= lat <= 90


def main():
    path = Path(__file__).resolve().parents[1] / "data/adams-wa/places.draft.json"
    places = json.loads(path.read_text())["places"]
    incomplete = 0
    for item in places:
        record = item["record"]
        issues = []
        if not record.get("address", "").strip():
            issues.append("missing address")
        if not valid_point(record.get("location")):
            issues.append("missing or invalid destination coordinates")
        if issues:
            incomplete += 1
        print(
            f"{record['name']}: {', '.join(issues) if issues else 'routing fields present; verify entrance accuracy'}"
        )
    print(f"{len(places) - incomplete}/{len(places)} destinations have routing fields present.")
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
