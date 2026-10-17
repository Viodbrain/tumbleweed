# Python data layer: teammate handoff

## Setup

Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
```

Set `MONGODB_URI` and `MONGODB_DB=tumbleweed` privately in `.env.local`, or in
the deployment environment. Deployment variables take priority. Ensure Atlas
allows the backend host's IP. Never commit the URI or include it in error logs.

```sh
.venv/bin/python -m scripts.setup_indexes --apply
.venv/bin/python scripts/test_mongodb.py
.venv/bin/python -m scripts.find_food --zip 99344 --snap
.venv/bin/python -m scripts.list_events --zip 99344
```

## Integration

```python
from app.db import get_db
from app.data import find_food, list_events, resolve_point
from app.models import FindFoodArgs

places = await find_food(FindFoodArgs(zip="99344", accepts_snap=True, limit=3))
events = await list_events(zip="99344", days=14)
point = await resolve_point(city="othello")
```

The production functions live in `backend/app/data.py` and are asynchronous,
matching the brain already on main. Run the backend from `backend/` so its `app`
package resolves. Use `get_db()` for the shared async cached connection.
The older synchronous `lib/` helpers are for the standalone root scripts only.
The brain still owns user
and message writes, subscription commands, conversation memory, and reply text.

`find_food` supports `zip`, `city`, `lat`, `lng`, `kind`, `accepts_snap`,
`open_day`, and `limit`. Coordinates take priority over ZIP, then city.
ZIPs are strings. Kinds are foodbank/grocery/market/meal; days are mon through
sun. Results are typed PlaceResult models with `distance_mi`, nearest first,
within 40 miles. ZIP/town distances are approximate straight-line distances
from a representative point, not driving distance or distance from someone's
home. Unknown open days do not match a day filter; day filtering does not
establish that a place is open right now or on a holiday.

`resolve_point` returns a ResolvedPoint model with zip/location fields, or None.
City matching is normalized exact-name matching; ambiguous cities choose the
lowest ZIP deterministically. Coverage is currently Othello only.

`list_events` returns at most five typed FoodEvent models, ordered by
start time, within 40 miles, from now through the next 14 days by default.
Store `starts_at` as a UTC BSON datetime per the current backend model, not an
ISO string. Parse timezone-aware ISO input when importing. Date-range filtering
excludes non-date values. No verified events have been seeded yet,
so an empty list is expected. Do not invent demo events as real resources.

Invalid search inputs return [] (or None for resolve_point). Database failures
propagate: the brain should catch PyMongoError/RuntimeError and use the agreed
error reply. An outage must not be presented as no resources available.

## Current dataset and remaining work

- Atlas contains ZIP 99344 and two SNAP grocery stores: Walmart and Lep-Re-Kon.
- Lep-Re-Kon has unknown weekly days, so Saturday-filtered results currently
  contain only Walmart. Never promise three results when fewer match.
- Food bank address and coordinates are recorded in the research draft, but it
  remains excluded because the shared boolean SNAP field cannot express unknown
  or non-retail status. Resolve its treatment with the team before import.
- No Google Maps key or routing API is required for the chosen distances.
- Integration now preserves the async signatures and Pydantic types from the
  backend scaffold pulled from main (8d23efe). No shared models or AI files were changed.

Reviewed seed data and provenance are in `data/adams-wa/`. Re-running
`scripts/seed_adams.py --apply` upserts only the listed records and does not delete
other data. `data/adams-wa/places.draft.json` is research, never a live seed file.

MongoDB config precedence: deployed environment, backend/.env.local, backend/.env,
then root .env.local. Existing standalone scripts still use root .env.local.
