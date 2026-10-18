import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.models import GeoPoint, PlaceResult


def _place() -> PlaceResult:
    return PlaceResult(
        _id="private-id",
        name="Example Pantry",
        kind="foodbank",
        address="1 Main St, Othello, WA 99344",
        location=GeoPoint(coordinates=(-119.17, 46.82)),
        hours="Mon 10am-2pm",
        days=["mon"],
        accepts_snap=True,
        phone="555-0100",
        notes="SNAP status is provider-specific.",
        voice_notes="Call ahead.",
        region="rural",
        distance_mi=1.234,
    )


def test_places_tool_requires_key_and_returns_minimal_fields(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_KEY", "test-key")
    from app import data
    from app.main import app

    monkeypatch.setattr(data, "find_food", AsyncMock(return_value=[_place()]))
    client = TestClient(app)

    unauthorized = client.post(
        "/api/elevenlabs/places/search",
        json={"conversation_id": "call-123", "zip": "99344"},
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/api/elevenlabs/places/search",
        headers={"X-ElevenLabs-Webhook-Key": "test-key"},
        json={"conversation_id": "call-123", "zip": "99344", "accepts_snap": True, "limit": 5},
    )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result == {
        "name": "Example Pantry",
        "address": "1 Main St, Othello, WA 99344",
        "distance_mi": 1.2,
        "hours": "Mon 10am-2pm",
        "phone": "555-0100",
        "notes": "Call ahead.",
    }
    assert "accepts_snap" not in result
    assert "private-id" not in response.text
    assert "coordinates" not in response.text


def test_context_save_requires_exact_evidence(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_KEY", "test-key")
    from app import user_context
    from app.main import app

    save = AsyncMock(return_value={"food_preferences": ["vegan"]})
    monkeypatch.setattr(user_context, "save_context", save)
    client = TestClient(app)
    headers = {"X-ElevenLabs-Webhook-Key": "test-key"}

    response = client.post(
        "/api/elevenlabs/users/context",
        headers=headers,
        json={
            "conversation_id": "call-123",
            "user_text": "I am vegan",
            "evidence": "vegan",
            "food_preferences": ["vegan"],
        },
    )
    assert response.status_code == 200
    save.assert_awaited_once_with("voice:call-123", {"food_preferences": ["vegan"]})

    invalid = client.post(
        "/api/elevenlabs/users/context",
        headers=headers,
        json={
            "conversation_id": "call-123",
            "user_text": "I need food",
            "evidence": "vegan",
            "food_preferences": ["vegan"],
        },
    )
    assert invalid.status_code == 422


def test_context_identity_is_conversation_scoped(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_KEY", "test-key")
    from app import user_context
    from app.main import app

    save = AsyncMock(return_value={"food_preferences": ["vegan"]})
    monkeypatch.setattr(user_context, "save_context", save)
    client = TestClient(app)

    response = client.post(
        "/api/elevenlabs/users/context",
        headers={"X-ElevenLabs-Webhook-Key": "test-key"},
        json={
            "conversation_id": "call-123",
            "user_text": "I am vegan",
            "evidence": "I am vegan",
            "food_preferences": ["vegan"],
        },
    )
    assert response.status_code == 200
    assert "caller_phone_number" not in response.text


def test_post_call_verifies_signature_and_deduplicates(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "secret")
    from app.main import app

    class Collection:
        def __init__(self):
            self.ids = set()

        async def insert_one(self, document):
            if document["_id"] in self.ids:
                raise DuplicateKeyError("duplicate")
            self.ids.add(document["_id"])

    collection = Collection()
    monkeypatch.setattr(
        "app.routes.elevenlabs.get_db",
        lambda: SimpleNamespace(voice_calls=collection),
    )
    payload = {
        "type": "post_call_transcription",
        "data": {
            "conversation_id": "call-123",
            "agent_id": "agent-1",
            "transcript": [{"role": "user", "message": "hello"}],
        },
    }
    raw = json.dumps(payload, separators=(",", ":"))
    timestamp = str(int(time.time()))
    digest = hmac.new(
        b"secret",
        f"{timestamp}.{raw}".encode(),
        hashlib.sha256,
    ).hexdigest()
    headers = {"elevenlabs-signature": f"t={timestamp},v0={digest}"}
    client = TestClient(app)

    first = client.post("/api/elevenlabs/post-call", content=raw, headers=headers)
    second = client.post("/api/elevenlabs/post-call", content=raw, headers=headers)
    assert first.json() == {"ok": True}
    assert second.json() == {"ok": True, "duplicate": True}

    invalid = client.post(
        "/api/elevenlabs/post-call",
        content=raw,
        headers={"elevenlabs-signature": "t=not-a-number,v0=bad"},
    )
    assert invalid.status_code == 401
