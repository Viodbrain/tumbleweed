# Adams and Ferry county food-resource coverage

Prepared and loaded into Atlas October 17, 2026. The datasets have 20 ZIP-area origins and 23 resources:
14 SNAP groceries/general stores, eight pantries, and one restricted meal site.
This is a curated resource inventory, not a claim to list every food provider.

## ZIP scope

We include every 2020 Census ZCTA with land intersecting Adams (53001) or Ferry
(53019), using the Census county relationship file. Some ZIP areas cross county
boundaries; the postal town can be outside the target county. This is geographic
search coverage, not an authoritative inventory of all current USPS ZIPs.

Adams (11): 98832 Marlin, 98857 Warden, 99032 Sprague, 99105 Benge,
99159 Odessa, 99169 Ritzville, 99326 Connell, 99333 Hooper, 99341 Lind,
99344 Othello, and 99371 Washtucna.

Ferry (9): 99118 Curlew, 99121 Danville, 99138 Inchelium, 99140 Keller,
99141 Kettle Falls, 99146 Laurier, 99150 Malo, 99160 Orient, and 99166 Republic.

Coordinates use 2025 Census ZCTA internal points, except the previously verified
Othello town point retained for compatibility. Postal town labels come from
GeoNames postal data. Neither a ZCTA point nor a town point is a user's actual
location. County overlap fractions and source URLs are in `county-sources.json`.
Legacy codes 99107, 99327, and 99332 occur in older references but lack records in
the chosen ZCTA scope; they are not introduced as verified current origins.
PO-box-only or other non-ZCTA codes require separate postal verification.

## Resource verification

Existing Othello/Curlew resources remain. New conventional grocery records use
the current USDA SNAP retailer layer for authorization and location; provider
pages supply hours/phone where available. Unknown values are null or [], never
fabricated. The USDA snapshot contains other convenience/market records that
have not all been promoted into the curated dataset.

New pantries cover Ritzville, Lind, Washtucna, Republic, Orient and Kettle Falls.
Kettle Falls is a neighboring-county provider; being geographically nearby does
not establish service eligibility. Washtucna's museum page confirms its service
area includes Benge and Hooper. Lind's pantry is documented as a recent DSHS
outreach venue, but the recurring food pickup schedule and phone remain unknown.
The dated DSHS outreach hours were not copied as pantry hours or seeded as an event.

Keller and Inchelium stores have operator addresses differing from the USDA
labels. We use current operator addresses and operator-linked map points,
recording the discrepancy rather than pairing a new address with an old point.
No store point or interpolated address establishes an exact public entrance.

Keller's meal site is restricted to eligible seniors/disabled adults. Its notes
preserve eligibility and advise calling about cost; it is not represented as an
unrestricted free meal. The Inchelium meal site remains excluded pending reliable
stored coordinates. Tribal commodity distribution can have SNAP-related
eligibility restrictions and must not be conflated with free public pantries.

## Known schedule limitations

- Curlew pantry: first and third Thursdays only; a weekday match does not prove
  opening on a particular Thursday.
- Ferry County Co-op: seasonal winter hours currently stored.
- Othello/Ritzville: operator or city hours differ from WA211. Notes disclose
  the discrepancy and advise calling.
- Lind/Washtucna and several stores: pickup/business hours unverified.
- Holidays, live stock, transport, eligibility and driving routes are not verified.

`accepts_snap=false` on a free pantry denotes no retail SNAP purchase for that
service; it does not exclude SNAP recipients. Meal service is likewise distinct
from an EBT checkout. Search for free pantries without `accepts_snap=True`.

## Load and check

From the repository root with `backend/.env` configured:

```sh
.venv/bin/python -m scripts.seed_adams --dataset adams-wa
.venv/bin/python -m scripts.seed_adams --dataset ferry-wa
.venv/bin/python -m scripts.seed_adams --dataset adams-wa --apply
.venv/bin/python -m scripts.seed_adams --dataset ferry-wa --apply
```

The seed verifies persisted IDs independently from geographic queries, then
checks each ZIP origin. A county can extend beyond 40 miles, so all places need
not be near its first ZIP. Upserts do not delete other regions or overwrite
nonlisted IDs. The database-free tests check models, provenance, ZIP coverage,
coordinate order, and nearby pantry/SNAP candidates using straight-line distance.

Validation: 75 backend tests and backend lint passed. Atlas verification confirmed
all 23 resource records match the seed files and all 20 ZIPs resolve, sort nearby
results correctly, and return pantry and SNAP candidates within the radius.
