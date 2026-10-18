"""Owner: A. Webhook smoke test: signed event -> dedupe -> reply -> send (Photon + Mongo faked)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError
from standardwebhooks import Webhook

SECRET = "whsec_" + base64.b64encode(b"tumbleweed-test-secret-32-bytes!").decode()


class FakeCollection:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    async def insert_one(self, doc: dict[str, Any]) -> None:
        if doc["_id"] in self.ids:
            raise DuplicateKeyError("dup")
        self.ids.add(doc["_id"])


class FakeDb:
    def __init__(self) -> None:
        self.webhook_events = FakeCollection()


def _event(message_id: str = "msg_1", kind: str = "human") -> dict[str, Any]:
    return {
        "id": "evt_1",
        "type": "message.received",
        "data": {
            "id": message_id,
            "platform": "imessage",
            "status": "received",
            "sentBy": {"kind": kind, "handle": "+14155550123", "id": "usr_h", "platform": "imessage"},
            "receivedBy": {"kind": "agent", "handle": "+14155550188", "id": "usr_a", "platform": "imessage"},
            "space": {"id": "spc_1", "kind": "direct", "platform": "imessage"},
            "content": {"type": "text", "format": "plain", "text": "  98101  "},
        },
    }


def _signed(payload: dict[str, Any]) -> tuple[str, dict[str, str]]:
    body = json.dumps(payload)
    ts = datetime.now(UTC)
    sig = Webhook(SECRET).sign("wh_1", ts, body)
    return body, {"webhook-id": "wh_1", "webhook-timestamp": str(int(ts.timestamp())), "webhook-signature": sig}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[dict[str, Any]], list[Any]]:
    monkeypatch.setenv("PHOTON_WEBHOOK_SECRET", SECRET)
    from app.main import app
    from app.routes import photon as route

    sent: list[dict[str, Any]] = []
    replies: list[Any] = []
    db = FakeDb()

    async def fake_send_text(**kwargs: Any) -> None:
        sent.append(kwargs)

    async def fake_reply(args: Any) -> str:
        replies.append(args)
        return "1. Stub Food Bank (0.8 mi)"

    monkeypatch.setattr(route, "get_db", lambda: db)
    monkeypatch.setattr(route, "send_text", fake_send_text)
    monkeypatch.setattr(route, "reply", fake_reply)
    return TestClient(app), sent, replies


def test_replies_once_and_dedupes(client: tuple[TestClient, list[dict[str, Any]], list[Any]]) -> None:
    http, sent, replies = client
    body, headers = _signed(_event())
    assert http.post("/api/photon", content=body, headers=headers).json() == {"ok": True}
    assert replies[0].text == "98101" and replies[0].channel == "imessage"
    assert replies[0].photon.space_id == "spc_1" and replies[0].photon.agent_id == "usr_a"
    assert [s["idempotency_key"] for s in sent] == ["reply:msg_1"]  # fast reply -> no ack

    body, headers = _signed(_event())
    assert http.post("/api/photon", content=body, headers=headers).json()["duplicate"] is True
    assert len(sent) == 1


def test_ignores_own_messages(client: tuple[TestClient, list[dict[str, Any]], list[Any]]) -> None:
    http, sent, _ = client
    body, headers = _signed(_event(message_id="msg_2", kind="agent"))
    assert http.post("/api/photon", content=body, headers=headers).json()["ignored"] is True
    assert sent == []


def test_rejects_bad_signature(client: tuple[TestClient, list[dict[str, Any]], list[Any]]) -> None:
    http, _, _ = client
    body, headers = _signed(_event())
    headers["webhook-signature"] = "v1,AAAA"
    assert http.post("/api/photon", content=body, headers=headers).status_code == 401


def test_grouped_text_parts_are_joined() -> None:
    from app.photon_client import extract_inbound

    event = _event(message_id="msg_3")
    event["data"]["content"] = {
        "type": "group",
        "parts": [
            {"type": "text", "format": "plain", "text": "99344"},
            {"type": "text", "format": "plain", "text": " need free food services, can drive to food banks"},
            {"type": "image", "url": "https://example.com/photo.jpg"},
        ],
    }
    inbound = extract_inbound(event)
    assert inbound is not None
    assert inbound.text == "99344 need free food services, can drive to food banks"


def test_group_without_text_is_ignored() -> None:
    from app.photon_client import extract_inbound

    event = _event(message_id="msg_4")
    event["data"]["content"] = {"type": "group", "parts": [{"type": "image", "url": "https://example.com/a.jpg"}]}
    assert extract_inbound(event) is None
