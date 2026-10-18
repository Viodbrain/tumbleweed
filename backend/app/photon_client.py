"""Owner: A. Photon v2 Beta client helpers (package: photonhq-api, import: photon_api)."""

from __future__ import annotations

import os
from typing import Any

from photon_api import AsyncPhoton
from photon_api.rpc_generated import SendMessageInput
from pydantic import BaseModel

from app.models import Channel

_client: AsyncPhoton | None = None


def photon() -> AsyncPhoton:
    global _client
    if _client is None:
        key = os.getenv("PHOTON_API_KEY")
        if not key:
            raise RuntimeError("PHOTON_API_KEY is not set")
        _client = AsyncPhoton(headers={"Authorization": f"Bearer {key}"}, timeout=10.0)
    return _client


class Inbound(BaseModel):
    message_id: str
    space_id: str
    agent_id: str
    handle: str
    text: str
    channel: Channel


def _obj(v: Any) -> dict[str, Any] | None:
    return v if isinstance(v, dict) else None


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) and v else None


def _find_message(event: Any) -> dict[str, Any] | None:
    """Event type names aren't documented yet, so match on the message shape
    (documented in the Beta iMessage walkthrough) wherever it sits in the event."""
    ev = _obj(event)
    if ev is None:
        return None
    data = ev.get("data")
    data_obj = _obj(data) or {}
    for c in (data, data_obj.get("message"), data_obj.get("object"), ev.get("message"), ev):
        m = _obj(c)
        if m and _obj(m.get("sentBy")) and _obj(m.get("space")) and _obj(m.get("content")):
            return m
    return None


def _content_text(content: dict[str, Any]) -> str:
    """Text of a message. iMessage can send one message as a "group" of parts (e.g. a ZIP and a
    sentence); join their text parts and ignore attachments, so the user still gets an answer."""
    if content.get("type") == "text":
        return content.get("text").strip() if isinstance(content.get("text"), str) else ""
    if content.get("type") == "group" and isinstance(content.get("parts"), list):
        texts = [_content_text(p) for p in content["parts"] if isinstance(p, dict)]
        return " ".join(t for t in texts if t)
    return ""


def extract_inbound(event: Any) -> Inbound | None:
    m = _find_message(event)
    if m is None:
        return None
    sent_by, space, content = m["sentBy"], m["space"], m["content"]
    received_by = _obj(m.get("receivedBy"))

    if m.get("status") != "received":
        return None
    if sent_by.get("kind") != "human":  # never answer our own messages
        return None
    if received_by is None or received_by.get("kind") != "agent":
        return None
    if space.get("kind") != "direct":
        return None
    text = _content_text(content)
    if not text:
        return None

    platform = m.get("platform")
    channel: Channel | None = "imessage" if platform == "imessage" else "sms" if platform == "sms" else None
    fields = {
        "message_id": _str(m.get("id")),
        "space_id": _str(space.get("id")),
        "agent_id": _str(received_by.get("id")),
        "handle": _str(sent_by.get("handle")),
    }
    if channel is None or not text or any(v is None for v in fields.values()):
        return None
    return Inbound(text=text, channel=channel, **fields)


async def send_text(
    *,
    space_id: str,
    sender_id: str,
    text: str,
    idempotency_key: str,
    parent_message_id: str | None = None,
) -> None:
    project_id = os.getenv("PHOTON_PROJECT_ID")
    if not project_id:
        raise RuntimeError("PHOTON_PROJECT_ID is not set")
    body: dict[str, Any] = {
        "spaceId": space_id,
        "senderId": sender_id,
        "content": {"type": "text", "format": "plain", "text": text},
    }
    if parent_message_id:
        body["parentMessageId"] = parent_message_id
    await photon().projects.send_message(
        SendMessageInput.model_validate(
            {"path": {"id": project_id}, "headers": {"idempotency-key": idempotency_key}, "body": body}
        )
    )
