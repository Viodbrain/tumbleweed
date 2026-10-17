"""Exercise the module seed command with more than three records, without Atlas."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.parametrize("dataset", ["adams-wa", "ferry-wa"])
async def test_seed_verifies_more_than_three_places(tmp_path, monkeypatch, dataset):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from scripts import seed_adams

    folder = tmp_path / "data" / dataset
    folder.mkdir(parents=True)
    point = {"type": "Point", "coordinates": [-119.16, 46.82]}
    records = [
        {
            "_id": str(i),
            "address": "Test only",
            "name": "Test only",
            "location": point,
            "accepts_snap": i % 2 == 0,
            "days": [],
        }
        for i in range(4)
    ]
    (folder / "places.json").write_text(json.dumps(records))
    (folder / "zips.json").write_text(
        json.dumps(
            [
                {"_id": "99344", "city": "othello", "state": "WA", "location": point},
            ]
        )
    )
    collection = SimpleNamespace(
        bulk_write=AsyncMock(
            return_value=SimpleNamespace(
                upserted_count=4,
                matched_count=0,
                modified_count=0,
            )
        )
    )
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=[dict(r, distance_m=100) for r in records]))
    database = Mock()
    database.__getitem__ = Mock(return_value=collection)
    database.zips.find_one = AsyncMock(return_value={"location": point})
    database.places.aggregate = AsyncMock(return_value=cursor)
    monkeypatch.setattr(seed_adams, "Path", lambda _: tmp_path / "scripts/seed_adams.py")
    monkeypatch.setattr(seed_adams, "get_db", lambda: database)
    monkeypatch.setattr(seed_adams, "apply_indexes", AsyncMock())
    monkeypatch.setattr(seed_adams, "close_db", AsyncMock())
    monkeypatch.setattr("sys.argv", ["scripts.seed_adams", "--dataset", dataset, "--apply"])
    assert await seed_adams.main() == 0
    pipeline = database.places.aggregate.call_args.args[0]
    assert not any("$limit" in stage for stage in pipeline)
    assert "accepts_snap" not in pipeline[0]["$geoNear"]["query"]
