"""Data input guards must not contact Atlas."""

from unittest.mock import Mock

import pytest

from app import data
from app.models import FindFoodArgs


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    mocked = Mock(side_effect=AssertionError("Unexpected database access"))
    monkeypatch.setattr(data, "get_db", mocked)
    yield mocked


@pytest.mark.parametrize(
    "lat,lng",
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
        (None, 0),
        (0, None),
        (float("nan"), 0),
        (0, float("inf")),
    ],
)
async def test_invalid_coordinates(lat, lng):
    assert await data.find_food(FindFoodArgs(lat=lat, lng=lng)) == []


async def test_zero_limit():
    assert await data.find_food(FindFoodArgs(zip="99344", limit=0)) == []


@pytest.mark.parametrize("days", [0, -1, 1.5, "14", None, True, 10**20])
async def test_invalid_event_window(days):
    assert await data.list_events(zip="99344", days=days) == []


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"zip": "bad"},
        {"zip": "1234"},
        {"zip": "123456"},
        {"zip": 99344},
        {"zip": " "},
        {"city": " "},
        {"city": []},
    ],
)
async def test_bad_location_input(query):
    assert await data.resolve_point(**query) is None
