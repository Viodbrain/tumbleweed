# Python data layer: teammate handoff

## Setup

Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
```

Set `MONGODB_URI` and `MONGODB_DB=tumbleweed` privately in `backend/.env`, or in
the deployment environment. Deployment variables take priority. Ensure Atlas
allows the backend host's IP. Never commit the URI or include it in error logs.

```sh
.venv/bin/python -m scripts.setup_indexes --apply
.venv/bin/python -m scripts.seed_adams --apply
.venv/bin/python -m scripts.seed_adams --dataset ferry-wa --apply
.venv/bin/python -m scripts.test_mongodb
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
All CLI scripts reuse this same async implementation; the duplicate sync layer was removed.
The brain still owns user
and message writes, subscription commands, conversation memory, and reply text.
Persistent food preference context and reset behavior are documented in
`data/USER_CONTEXT.md`. Every channel inherits them through `reply()`.

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
lowest ZIP deterministically. Coverage includes all 20 Census ZCTAs intersecting Adams/Ferry counties (11 and 9
respectively), including cross-county areas. New origins use Census ZCTA reference
points; the original Othello town point is preserved. See `data/COUNTY_COVERAGE.md`.

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

- The Adams seed contains 11 ZIP areas and 11 resources; Ferry contains nine ZIP
  areas and 12 resources. Both counties have pantry and SNAP candidates within
  40 straight-line miles of each seeded reference point. This does not establish
  eligibility, availability, or a drivable route.
- Run both county seed commands. New provenance is in each `county-sources.json`;
  earlier records keep their original research/source files.
- Unknown hours/phones remain null and unknown weekly days remain []. Such
  records are excluded by open-day filters. Never promise three results when
  fewer match. Cross-county resources can appear in a nearby search.
- Preserve the Curlew first/third Thursday restriction, co-op seasonal schedule,
  meal-site eligibility restrictions, and provider-hour discrepancies in replies.
- Othello Food Bank is free distribution, with `accepts_snap=false` denoting no
  SNAP retail purchase for that service. SNAP recipients may still use it.
  Search `kind="foodbank"` without `accepts_snap=True` for free food banks.
  Public hours use the operator's Mon-Wed 1-4pm; WA211 differs, so notes advise
  calling. Thursday is restricted senior pickup and excluded from public days.
- No Google Maps key or routing API is required for the chosen distances.
- Integration now preserves the async signatures and Pydantic types from the
  backend scaffold pulled from main (8d23efe). No shared models or AI files were changed.

Reviewed seed data and provenance are in `data/adams-wa/`. Re-running
`python -m scripts.seed_adams --apply` upserts only the listed records and does not delete
other data. `data/adams-wa/places.draft.json` is research, never a live seed file.

Configuration is loaded once through `backend/app/config.py`:
process environment > `backend/.env` > legacy root `.env.local`.
Use only `backend/.env` for new local setups. Do not create `.env.local` variants;
the root fallback only supports migration. The backend and every database CLI use
this loader. Share secrets privately, never in source control or review comments.
The database client and database name are cached after the first connection.

## ElevenLabs voice endpoints

The FastAPI service exposes authenticated ElevenLabs integrations without a
separate worker process:

- `POST /api/elevenlabs/places/search` requires a conversation ID, accepts the
  existing location/filter arguments, and returns at most five minimal place
  records plus `spoken_text`.
  Internal IDs, coordinates, region, and SNAP status are not returned. SNAP may
  be used as an explicit search filter, but the response uses neutral wording.
- `GET /api/elevenlabs/users/context` returns only the conversation's known ZIP
  and language.
- `POST /api/elevenlabs/users/context` saves only bounded food preferences and
  requires an exact evidence quote from the supplied `user_text`.
- `DELETE /api/elevenlabs/users/context` clears the caller's context and
  message history using the existing `FORGET` semantics.
- `POST /api/elevenlabs/post-call` accepts ElevenLabs HMAC-signed
  `post_call_transcription` events and stores the full event in `voice_calls`,
  deduplicated by conversation ID. There is no TTL policy.

In-call tools require the `X-ElevenLabs-Webhook-Key` header and
`ELEVENLABS_WEBHOOK_KEY`. Post-call webhooks require the
`elevenlabs-signature` header and `ELEVENLABS_WEBHOOK_SECRET`. Voice context is
scoped to `voice:<conversation_id>` because a caller phone number supplied by a
voice tool is not independently verifiable. Post-call records store normalized
metadata, transcript, and analysis (not an unbounded raw payload), are capped
at 8 MiB per request, and have no automatic TTL policy.

Index setup includes unique `users.handle`, message history/feed indexes, and
`webhook_events.received_at`; the webhook message ID uses MongoDB's automatic
unique `_id` index. No TTL policy is imposed. Existing duplicate user handles
must be resolved before the unique index can be created.

Follow-ups: full Washington coverage, current verified events, Seattle data,
unknown hours/phones, and provider confirmation. Historical/non-ZCTA ZIPs are
not silently treated as current geographic origins. No events were invented.
