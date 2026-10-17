"""Owner: A. Endpoints the /demo page (D) calls."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.brain import reply
from app.db import get_db
from app.models import ReplyArgs

router = APIRouter()


class ChatIn(BaseModel):
    handle: str = Field(pattern=r"^web:[A-Za-z0-9-]{1,64}$")
    text: str = Field(min_length=1, max_length=1000)


@router.post("/api/chat")
async def chat(body: ChatIn) -> dict[str, str]:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is empty")
    return {"reply": await reply(ReplyArgs(handle=body.handle, text=text, channel="web"))}


@router.get("/api/feed")
async def feed() -> dict[str, list[dict[str, Any]]]:
    cursor = (
        get_db()
        .messages.find(
            {"direction": "in", "location": {"$ne": None}},
            {"_id": 0, "location": 1, "channel": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(100)
    )
    points = [
        {
            "lng": doc["location"]["coordinates"][0],
            "lat": doc["location"]["coordinates"][1],
            "channel": doc["channel"],
            "created_at": doc["created_at"].isoformat(),
        }
        async for doc in cursor
    ]
    return {"points": points}
