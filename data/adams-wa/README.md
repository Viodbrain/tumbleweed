# Adams County, Washington: initial Othello dataset

Prepared October 17, 2026. Target ZIP: 99344. Loaded the reviewed ZIP and two
grocery records into Atlas on October 17, 2026. The food bank remains draft.

## Location

`zips.json` follows the shared ZipDoc shape. Coordinates use longitude first.
The point is the GeoNames Othello populated-place location, an approximate search
origin for this ZIP, not a ZIP boundary centroid or the user's precise location.

- Coordinates: https://www.geonames.org/5805879/othello.html
- ZIP and county association: https://dor.wa.gov/exemptions/adams

## Resource research

`places.draft.json` contains three candidate resources, their sources, and pending
verification tasks. It is a research format, not the application's Place schema.
Do not import it into the live places collection. Unknown
SNAP status must be resolved before producing seed-ready records. Do not use
town-center coordinates for individual businesses or convert unknown SNAP status
to false.

Othello Food Bank's public pickup days exclude its restricted Thursday senior
program. Office hours are not food pickup hours. The operator's site mentions a
move; the user subsequently confirmed 949 E Main St as the current pickup
address in chat. Its address was matched by the Census geocoder; this is a
street-interpolated point, not a verified entrance. Source pages were
reviewed online; no provider has been contacted by this assistant.

## Data needed for future driving distances

The shared Place schema already has the destination fields needed for routing:
`_id`, `name`, full `address` (street, city, state, ZIP), and `location` as a
GeoJSON Point with `[longitude, latitude]`. Use the public pickup/customer
entrance rather than a mailing address or town center. Events likewise need
their actual venue address and coordinates.

No Google Place ID or per-place distance field is required. Keep the agreed
shared schema unchanged. Record coordinate sources and verification in the
research draft alongside each record.

The origin comes from the user's request. The ZIP point is an approximate origin;
label results as from central Othello when it is used. A precise user origin is
needed for a distance from their actual location. Do not store personal starting
addresses in this public seed dataset.

Calculate driving distance and duration at request time. They depend on origin,
travel mode, and routing options and are not permanent attributes of a place.
Keep MongoDB straight-line distance distinct from Google driving distance in
the eventual response contract; coordinate that contract with the AI owner.

Run `.venv/bin/python scripts/check_routing_data.py` to check destination
readiness. This reads local files only and does not call Google or modify Atlas.

Walmart's store-specific page supports its SNAP eligibility, hours, address, and
phone. Harvest Foods' listing supports its address, phone, and time range, but
does not explicitly establish all weekly days. Its `days` therefore remains `[]`.

The current USDA SNAP retailer dataset matches both grocery addresses and
provides their coordinates and SNAP acceptance. Source:
https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0
The dataset item `8b260f9a10b0459aa441ad8588c2251c` is linked by USDA's
https://www.fns.usda.gov/snap/retailer-locator page. Retrieved October 17, 2026.

`places.json` contains the two grocery records that match the shared schema.
The food bank remains draft because SNAP acceptance is unknown and the agreed
schema requires a boolean. Free distribution is not the same as accepting EBT
for a purchase; ask the data/brain owners how to represent non-retail resources
without mislabeling an unknown as false. Its phone is corroborated by Catholic
Charities Eastern Washington's parish social ministry listing.

All three records now have sourced coordinates, suitable as approximate points
for nearby searches. None has a separately verified entrance. Do not describe
these points as exact pickup entrances or route results as door-to-door accurate.

## Next steps

The initial seed succeeded: one ZIP, two groceries, and location indexes on
both collections, plus city and region indexes. A 40-mile SNAP-filtered search
returned Lep-Re-Kon (about 0.79 straight-line miles) and Walmart (about 1.30)
from the Othello town point.

To validate locally: `.venv/bin/python scripts/seed_adams.py`.
To upsert the reviewed records again: `.venv/bin/python scripts/seed_adams.py --apply`.
The script updates only the listed IDs and does not delete other records.

Python lookup is implemented in `lib/db.py` and `lib/data.py`. From the repo
root, install `scripts/requirements.txt` into your virtual environment, then run:

```sh
.venv/bin/python -m scripts.find_food --zip 99344 --snap
.venv/bin/python -m scripts.find_food --city othello --day sat
```

Backend integration: `from lib.data import find_food, resolve_point`.
Both functions take keyword arguments. `find_food` returns full place dictionaries
plus `distance_mi` (straight-line), sorted nearest first, within 40 miles. It
defaults to three results; current coverage has only two places. ZIP coordinates
are approximate. Unknown weekly days are excluded by day filters. These are
synchronous PyMongo functions; asynchronous callers should run them in a thread.
Database errors propagate for the brain to handle rather than looking like an
empty search. No HTTP endpoint or TypeScript adapter has been added.

Verified against Atlas: ZIP search, normalized city search, SNAP filter, Saturday
filter, and unknown ZIP. Invalid coordinates are rejected locally.

Remaining work: resolve food-bank SNAP representation, confirm Harvest Foods'
weekly days, verify entrances, and implement upcoming-event lookup.

No upcoming event is included until a current dated distribution is verified.
