"""Owner: A. Photon signed webhook -> reply() -> Photon sendMessage."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pymongo.errors import DuplicateKeyError
from standardwebhooks import Webhook, WebhookVerificationError

from app.brain import reply
from app.db import get_db
from app.models import PhotonMeta, ReplyArgs
from app.photon_client import Inbound, extract_inbound, send_text

log = logging.getLogger("tumbleweed.photon")
router = APIRouter()

ACK_AFTER_S = 1.5
ACK_TEXT = "Got it, looking now..."
_SIG_HEADERS = ("webhook-id", "webhook-timestamp", "webhook-signature")


@router.post("/api/photon")
async def photon_webhook(request: Request, background: BackgroundTasks) -> dict[str, Any]:
    secret = os.getenv("PHOTON_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="PHOTON_WEBHOOK_SECRET is not set")

    raw = await request.body()
    try:
        event = Webhook(secret).verify(raw, {h: request.headers.get(h, "") for h in _SIG_HEADERS})
    except WebhookVerificationError:
        log.warning("signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature") from None

    inbound = extract_inbound(event)
    if inbound is None:
        event_type = event.get("type") if isinstance(event, dict) else None
        log.info("ignored event type=%s", event_type)
        return {"ok": True, "ignored": True}

    try:
        await get_db().webhook_events.insert_one({"_id": inbound.message_id, "received_at": datetime.now(UTC)})
    except DuplicateKeyError:
        return {"ok": True, "duplicate": True}

    background.add_task(handle_inbound, inbound)
    return {"ok": True}


async def handle_inbound(m: Inbound) -> None:
    started = time.monotonic()
    task = asyncio.create_task(
        reply(
            ReplyArgs(
                handle=m.handle,
                text=m.text,
                channel=m.channel,
                photon=PhotonMeta(space_id=m.space_id, agent_id=m.agent_id, message_id=m.message_id),
            )
        )
    )

    done, _ = await asyncio.wait({task}, timeout=ACK_AFTER_S)
    acked = False
    if not done:
        try:
            await send_text(
                space_id=m.space_id, sender_id=m.agent_id, text=ACK_TEXT, idempotency_key=f"ack:{m.message_id}"
            )
            acked = True
        except Exception:
            log.exception("ack send failed for %s", m.message_id)

    text = await task  # reply() never raises by contract
    try:
        await send_text(
            space_id=m.space_id,
            sender_id=m.agent_id,
            parent_message_id=m.message_id,
            text=text,
            idempotency_key=f"reply:{m.message_id}",
        )
        log.info("in=%s ack=%s out_chars=%d ms=%d", m.message_id, acked, len(text), (time.monotonic() - started) * 1000)
    except Exception:
        log.exception("reply send failed for %s", m.message_id)
