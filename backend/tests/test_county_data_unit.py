"""Check the sourced county dataset without Atlas or external requests."""

import json
import math
from pathlib import Path

import pytest

from app.models import Place, ZipDoc

DATA = Path(__file__).resolve().parents[2] / "data"
EXPECTED = {
    "adams-wa": {"98832", "98857", "99032", "99105", "99159", "99169", "99326", "99333", "99341", "99344", "99371"},
    "ferry-wa": {"99118", "99121", "99138", "99140", "99141", "99146", "99150", "99160", "99166"},
}


def load(dataset, name):
    return json.loads((DATA / dataset / name).read_text())


@pytest.mark.parametrize("dataset", EXPECTED)
def test_county_schema_scope_and_provenance(dataset):
    zips = [ZipDoc.model_validate(row) for row in load(dataset, "zips.json")]
    places = [Place.model_validate(row) for row in load(dataset, "places.json")]
    assert {z.id for z in zips} == EXPECTED[dataset]
    assert len(zips) == len({z.id for z in zips})
    assert len(places) == len({p.id for p in places})
    provenance = load(dataset, "county-sources.json")
    assert {row["id"] for row in provenance["zips"]} == EXPECTED[dataset]
    for record in [*zips, *places]:
        lng, lat = record.location.coordinates
        assert -125 < lng < -116 and 45 < lat < 50  # detect swapped or foreign coordinates
    source_ids = {row["id"] for row in provenance["places"]}
    if dataset == "adams-wa":
        source_ids.update(row["record"]["_id"] for row in load(dataset, "places.draft.json")["places"])
    else:
        source_ids.update(row["id"] for row in load(dataset, "sources.json")["places"])
    assert {p.id for p in places} <= source_ids


def test_every_county_zip_has_pantry_and_snap_candidates_within_radius():
    places = [Place.model_validate(row) for dataset in EXPECTED for row in load(dataset, "places.json")]
    for dataset in EXPECTED:
        for row in load(dataset, "zips.json"):
            lng, lat = map(math.radians, row["location"]["coordinates"])
            nearby = []
            for place in places:
                plng, plat = map(math.radians, place.location.coordinates)
                h = math.sin((plat - lat) / 2) ** 2 + math.cos(lat) * math.cos(plat) * math.sin((plng - lng) / 2) ** 2
                miles = 3958.7613 * 2 * math.asin(min(1, math.sqrt(h)))
                if miles <= 40:
                    nearby.append(place)
            assert any(p.kind == "foodbank" for p in nearby), row["_id"]
            assert any(p.accepts_snap for p in nearby), row["_id"]
