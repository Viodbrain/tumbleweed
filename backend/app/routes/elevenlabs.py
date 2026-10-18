"""Authenticated ElevenLabs tools and post-call webhook ingestion."""

from __future__ import annotations

import hmac
import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from elevenlabs import ElevenLabs
from elevenlabs.errors import BadRequestError
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError

from app import data, user_context
from app.db import get_db
from app.models import Day, FindFoodArgs, PlaceKind

router = APIRouter()
_HANDLE = re.compile(r"^[A-Za-z0-9:_+.-]{1,128}$")
MAX_POST_CALL_BYTES = 8 * 1024 * 1024


class PlaceSearchRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_+.-]+$")
    zip: str | None = Field(default=None, pattern=r"^\d{5}$")
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    kind: PlaceKind | None = None
    accepts_snap: bool | None = None
    open_day: Day | None = None
    limit: int = Field(default=3, ge=1, le=5)


class ContextRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_+.-]+$")
    food_preferences: list[str] = Field(default_factory=list, max_length=8)
    user_text: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=2000)


def _evidence_matches_preferences(evidence: str, preferences: list[str]) -> bool:
    text = evidence.casefold()
    terms = {
        "vegetarian": ("vegetarian",),
        "vegan": ("vegan",),
        "halal": ("halal",),
        "kosher": ("kosher",),
        "no_pork": ("no pork", "avoid pork", "without pork", "don't eat pork"),
        "no_beef": ("no beef", "avoid beef", "without beef", "don't eat beef"),
        "no_seafood": ("no seafood", "avoid seafood", "without seafood", "don't eat seafood"),
        "no_preference": ("no preference", "anything is fine", "anything is okay"),
    }
    return all(any(term in text for term in terms.get(preference, ())) for preference in preferences)


def _require_tool_key(value: str | None) -> None:
    expected = os.getenv("ELEVENLABS_WEBHOOK_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="ELEVENLABS_WEBHOOK_KEY is not set")
    if not value or not hmac.compare_digest(value, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook key")


def _handle(conversation_id: str) -> str:
    if not _HANDLE.fullmatch(conversation_id):
        raise HTTPException(status_code=422, detail="conversation_id is invalid")
    return f"voice:{conversation_id}"


def _spoken_text(results: list[dict[str, Any]]) -> str:
    if not results:
        return "I couldn't find matching food resources within 40 miles."
    lines = []
    for index, place in enumerate(results, start=1):
        details = [f"{index}. {place['name']}", f"about {place['distance_mi']:.1f} miles away"]
        if place.get("hours"):
            details.append(place["hours"])
        if place.get("phone"):
            details.append(f"call {place['phone']}")
        lines.append(", ".join(details))
    return "I found these options: " + ". ".join(lines)


def _minimal_place(place: Any) -> dict[str, Any]:
    return {
        "name": place.name,
        "address": place.address,
        "distance_mi": round(place.distance_mi, 1),
        "hours": place.hours,
        "phone": place.phone,
        "notes": place.voice_notes,
    }


@router.post("/api/elevenlabs/places/search")
async def search_places(
    body: PlaceSearchRequest,
    x_elevenlabs_webhook_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_tool_key(x_elevenlabs_webhook_key)
    try:
        args = FindFoodArgs.model_validate(body.model_dump(exclude={"conversation_id"}))
        places = await data.find_food(args)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid place search arguments") from None
    except (PyMongoError, RuntimeError):
        raise HTTPException(status_code=503, detail="Place search is temporarily unavailable") from None
    results = [_minimal_place(place) for place in places]
    return {"results": results, "spoken_text": _spoken_text(results)}


@router.get("/api/elevenlabs/users/context")
async def get_context(
    conversation_id: str = Query(min_length=1, max_length=128),
    x_elevenlabs_webhook_key: str | None = Header(default=None),
) -> dict[str, str | None]:
    _require_tool_key(x_elevenlabs_webhook_key)
    user_handle = _handle(conversation_id)
    try:
        row = await get_db().users.find_one({"handle": user_handle}, {"_id": 0, "zip": 1, "lang": 1})
    except (PyMongoError, RuntimeError):
        raise HTTPException(status_code=503, detail="User context is temporarily unavailable") from None
    return {"zip": row.get("zip") if row else None, "lang": row.get("lang") if row else None}


@router.post("/api/elevenlabs/users/context")
async def save_context(
    body: ContextRequest,
    x_elevenlabs_webhook_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_tool_key(x_elevenlabs_webhook_key)
    if body.evidence not in body.user_text or not _evidence_matches_preferences(
        body.evidence, body.food_preferences
    ):
        raise HTTPException(status_code=422, detail="evidence must quote user_text exactly")
    user_handle = _handle(body.conversation_id)
    try:
        saved = await user_context.save_context(
            user_handle,
            {"food_preferences": body.food_preferences},
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid food preferences") from None
    except (PyMongoError, RuntimeError):
        raise HTTPException(status_code=503, detail="User context is temporarily unavailable") from None
    return {"saved": True, "fields": list(saved)}


@router.delete("/api/elevenlabs/users/context")
async def clear_context(
    conversation_id: str = Query(min_length=1, max_length=128),
    x_elevenlabs_webhook_key: str | None = Header(default=None),
) -> dict[str, bool]:
    _require_tool_key(x_elevenlabs_webhook_key)
    try:
        await user_context.forget_context(_handle(conversation_id))
    except (PyMongoError, RuntimeError):
        raise HTTPException(status_code=503, detail="User context is temporarily unavailable") from None
    return {"cleared": True}


@router.post("/api/elevenlabs/post-call")
async def post_call(request: Request) -> dict[str, bool]:
    secret = os.getenv("ELEVENLABS_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="ELEVENLABS_WEBHOOK_SECRET is not set")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_POST_CALL_BYTES:
                raise HTTPException(status_code=413, detail="Webhook payload is too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content length") from None
    raw = await request.body()
    if len(raw) > MAX_POST_CALL_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload is too large")
    signature = request.headers.get("elevenlabs-signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing ElevenLabs signature")
    try:
        event = ElevenLabs().webhooks.construct_event(
            rawBody=raw.decode("utf-8"),
            sig_header=signature,
            secret=secret,
        )
    except (BadRequestError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid ElevenLabs signature") from None
    if not isinstance(event, dict) or event.get("type") != "post_call_transcription":
        return {"ok": True}
    data_obj = event.get("data")
    if not isinstance(data_obj, dict) or not isinstance(data_obj.get("conversation_id"), str):
        raise HTTPException(status_code=422, detail="conversation_id is required")
    transcript = data_obj.get("transcript")
    if not isinstance(transcript, list):
        raise HTTPException(status_code=422, detail="transcript is required")
    try:
        await get_db().voice_calls.insert_one(
            {
                "_id": data_obj["conversation_id"],
                "event_type": event["type"],
                "received_at": datetime.now(UTC),
                "conversation_id": data_obj["conversation_id"],
                "agent_id": data_obj.get("agent_id"),
                "version_id": data_obj.get("version_id"),
                "metadata": data_obj.get("metadata"),
                "transcript": transcript,
                "analysis": data_obj.get("analysis"),
            }
        )
    except DuplicateKeyError:
        return {"ok": True, "duplicate": True}
    except (PyMongoError, RuntimeError):
        raise HTTPException(status_code=503, detail="Voice call storage is temporarily unavailable") from None
    return {"ok": True}
