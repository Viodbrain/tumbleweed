## County-wide expansion

The dataset now includes 9 Census ZIP areas and 12 resources.
See `../COUNTY_COVERAGE.md` for the geographic scope and limitations, and
`county-sources.json` for each new record's provenance. The material below
records the original Othello/Curlew rollout; its resource counts are historical.

# Curlew, Ferry County, Washington — ZIP 99118

Prepared and loaded into Atlas October 17, 2026. ZIP/city, SNAP and food-bank
filters were verified; Othello records remain available. Sources and verification caveats are in `sources.json`.

`zips.json` uses the Census 2025 ZCTA internal point for 99118. This is an
approximate ZIP-area origin, not central Curlew or a user's actual location.
All coordinates are GeoJSON `[longitude, latitude]`.

`places.json` contains Curlew Community Food Pantry, Danville Outpost, and Ferry
County Co-op in Republic. The stores are outside ZIP 99118 but within the
40-mile straight-line search radius. They are not claimed to be the nearest
possible stores or an exhaustive inventory. SNAP eligibility and store points
come from the current USDA retailer layer; business hours and phones come from
the operators. The pantry point is Census street-address interpolation.

The pantry distributes only on the first and third Thursdays, 9:30-11am. Its
`days=["thu"]` supports weekday discovery, not a guarantee of opening on a
particular date. Preserve the first/third restriction in user-facing replies.
WA211 lists walk-ins, no fees, and holiday closure. No SNAP purchase is required.

The co-op uses its current winter schedule. Summer hours differ and include
Sunday opening. Refresh the data at the seasonal change; do not promise summer
open-day results from the winter `days` list. Phone the provider before travel.

No exact public entrance has been verified. Distances are straight-line and
must never be presented as driving distances. No dated food events are invented
or generated from the recurring pantry schedule.

From the repository root, using the shared `backend/.env`:

```sh
.venv/bin/python -m scripts.seed_adams --dataset ferry-wa
.venv/bin/python -m scripts.seed_adams --dataset ferry-wa --apply
.venv/bin/python -m scripts.find_food --zip 99118
.venv/bin/python -m scripts.find_food --city curlew --snap
```

The existing seed command now accepts `--dataset`; its default remains
`adams-wa` for compatibility. Upserts affect only the dataset IDs and do not
delete Othello data. Run `kind="foodbank"` without `accepts_snap=True` to find
free distribution services.

Verified approximate straight-line distances from the ZIP reference point:
Curlew pantry 1.99 miles, Danville Outpost 9.09 miles, co-op 17.84 miles.
