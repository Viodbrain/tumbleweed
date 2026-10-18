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

## Secrets and environment variables

Use [`backend/.env.example`](../backend/.env.example) as the checklist of
variable names. It is only a template; do not put real values in it.

For local development, create `backend/.env` and fill in the values privately.
The application loads configuration in this order:

1. Process environment variables
2. `backend/.env`
3. Legacy root `.env.local` fallback

For Railway, enter the same variables in the service's **Variables** settings.
Do not upload `.env` files or commit secrets to GitHub. Railway injects those
variables into the running process at deploy time.

The variables come from different services:

- `MONGODB_URI` and `MONGODB_DB`: MongoDB Atlas connection details and database
  name.
- `PHOTON_API_KEY`, `PHOTON_PROJECT_ID`, and `PHOTON_WEBHOOK_SECRET`: Photon
  project credentials and the secret configured for Photon webhook signing.
- `ANTHROPIC_API_KEY` and `LLM_MODEL`: Anthropic API access and the Claude model
  name used by the backend.
- `ELEVENLABS_WEBHOOK_KEY`: a Tumbleweed-generated shared secret configured as
  the `X-ElevenLabs-Webhook-Key` header on ElevenLabs in-call tools.
- `ELEVENLABS_WEBHOOK_SECRET`: the signing secret generated/configured for the
  ElevenLabs post-call webhook. The backend verifies the
  `elevenlabs-signature` header with it.
- `DEFAULT_TZ` and `ALLOWED_ORIGINS`: non-secret application settings.

When a secret is missing, the affected integration fails explicitly; it is
not a value coworkers should guess or copy from source code. Share values
through the team's approved password manager or secret-sharing process. If a
secret appears in Git, chat, a ticket, or an accidentally committed local
file, treat it as compromised and rotate it at the issuing service.

```sh
.venv/bin/python -m scripts.setup_indexes --apply
.venv/bin/python -m scripts.test_mongodb
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
lowest ZIP deterministically. The production MongoDB database is the source of truth for ZIP coverage and food
resources. The repository retains reviewed county fixtures for offline validation
and controlled maintenance; those files are not loaded automatically by the
application.

`list_events` returns at most five typed FoodEvent models, ordered by
start time, within 40 miles, from now through the next 14 days by default.
Store `starts_at` as a UTC BSON datetime per the current backend model, not an
ISO string. Parse timezone-aware ISO input when importing. Date-range filtering
excludes non-date values. No verified events have been seeded yet,
so an empty list is expected. Do not invent demo events as real resources.

Invalid search inputs return [] (or None for resolve_point). Database failures
propagate: the brain should catch PyMongoError/RuntimeError and use the agreed
error reply. An outage must not be presented as no resources available.

## Current data operations

The backend reads places, ZIPs, and events from MongoDB. County JSON fixtures and
the explicit seeding/validation scripts are retained for offline tests and
controlled maintenance only; they are not a fallback data source and are not
loaded during application startup.

Unknown hours/phones remain null and unknown weekly days remain []. Such records
are excluded by open-day filters. Never promise three results when fewer match.
Distances are approximate straight-line distances from representative origins,
not driving distances.

Use `scripts.setup_indexes` only to create or verify indexes. Data changes must
go through the approved MongoDB/Atlas administration workflow with provenance
recorded there, rather than through application startup or ad hoc local files.

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
