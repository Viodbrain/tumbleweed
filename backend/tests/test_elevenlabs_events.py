from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.models import FoodEvent, GeoPoint, PlaceResult

KEY = {"X-ElevenLabs-Webhook-Key": "test-key"}


def _event(title: str, notes: str, hour_utc: int) -> FoodEvent:
    return FoodEvent(
        _id=f"e-{title}",
        title=title,
        place_name="Othello Food Bank",
        address="949 E Main St, Othello, WA 99344",
        location=GeoPoint(coordinates=(-119.17, 46.82)),
        starts_at=datetime(2026, 10, 19, hour_utc, 0, tzinfo=UTC),
        notes=notes,
        region="rural",
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_KEY", "test-key")
    monkeypatch.setenv("DEFAULT_TZ", "America/Los_Angeles")
    from app.main import app

    return TestClient(app)


def test_events_tool_requires_key(client):
    response = client.post("/api/elevenlabs/events/search", json={"conversation_id": "call-1", "zip": "99344"})
    assert response.status_code == 401


def test_events_tool_requires_a_location(client, monkeypatch):
    from app import data

    monkeypatch.setattr(data, "list_events", AsyncMock(return_value=[]))
    response = client.post("/api/elevenlabs/events/search", headers=KEY, json={"conversation_id": "call-1"})
    assert response.status_code == 422


def test_events_are_spoken_in_local_time_with_free_food_first(client, monkeypatch):
    from app import data

    events = [
        _event("School food drive", "Donation drop-off only; not a food pickup.", 17),
        _event("Food box pickup", "Free food. Call to confirm.", 20),
    ]
    list_events = AsyncMock(return_value=events)
    monkeypatch.setattr(data, "list_events", list_events)
    response = client.post(
        "/api/elevenlabs/events/search", headers=KEY, json={"conversation_id": "call-1", "zip": "99344", "days": 7}
    )
    assert response.status_code == 200
    list_events.assert_awaited_once_with(zip="99344", city=None, days=7)
    body = response.json()
    assert [e["title"] for e in body["results"]] == ["Food box pickup", "School food drive"]
    # 20:00 UTC on Oct 19 is 1 PM Pacific.
    assert body["results"][0]["when"] == "Monday, October 19 at 1 PM"
    assert body["spoken_text"].startswith("Here's what's coming up: 1. Food box pickup at Othello Food Bank, Monday")
    assert "location" not in body["results"][0] and "_id" not in body["results"][0]


def test_no_events_is_said_plainly(client, monkeypatch):
    from app import data

    monkeypatch.setattr(data, "list_events", AsyncMock(return_value=[]))
    response = client.post(
        "/api/elevenlabs/events/search", headers=KEY, json={"conversation_id": "call-1", "city": "Curlew"}
    )
    assert response.json() == {"results": [], "spoken_text": "I couldn't find any food events in the next 14 days."}


def test_events_database_outage_is_503(client, monkeypatch):
    from app import data

    monkeypatch.setattr(data, "list_events", AsyncMock(side_effect=PyMongoError("down")))
    response = client.post(
        "/api/elevenlabs/events/search", headers=KEY, json={"conversation_id": "call-1", "zip": "99344"}
    )
    assert response.status_code == 503


def test_place_at_town_center_is_right_in_town(client, monkeypatch):
    from app import data

    place = PlaceResult(
        _id="harvest-table",
        name="Harvest Table Community Pantry",
        kind="foodbank",
        address="1 Main St, Othello, WA 99344",
        location=GeoPoint(coordinates=(-119.17, 46.82)),
        region="rural",
        distance_mi=0.02,
    )
    monkeypatch.setattr(data, "find_food", AsyncMock(return_value=[place]))
    response = client.post(
        "/api/elevenlabs/places/search", headers=KEY, json={"conversation_id": "call-1", "zip": "99344"}
    )
    assert "Harvest Table Community Pantry, right in town" in response.json()["spoken_text"]
    assert "0.0 miles" not in response.json()["spoken_text"]
