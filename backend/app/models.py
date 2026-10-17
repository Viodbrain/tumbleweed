"""Shared contracts. Changing anything here needs all 4 teammates to agree."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlaceKind = Literal["foodbank", "grocery", "market", "meal"]
Channel = Literal["imessage", "sms", "web"]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Region = Literal["rural", "seattle"]


class GeoPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # (lng, lat) -- longitude FIRST


class _MongoDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Place(_MongoDoc):
    id: str = Field(alias="_id")  # string slug, e.g. "hope-pantry-omak"
    name: str
    kind: PlaceKind
    address: str
    location: GeoPoint
    hours: str | None = None  # human text, e.g. "Tue/Thu 10am-2pm"
    days: list[Day] = Field(default_factory=list)  # structured open days; [] = unknown
    accepts_snap: bool = False
    phone: str | None = None
    notes: str | None = None  # curated facts: "No ID required, Spanish spoken"
    region: Region


class PlaceResult(Place):
    distance_mi: float


class FoodEvent(_MongoDoc):
    id: str = Field(alias="_id")
    title: str
    place_name: str
    address: str
    location: GeoPoint
    starts_at: datetime  # stored as a BSON date (UTC)
    notes: str | None = None
    region: Region


class ZipDoc(_MongoDoc):
    id: str = Field(alias="_id")  # 5-digit ZIP
    city: str  # lowercase, e.g. "omak"
    state: str  # "WA"
    location: GeoPoint


class UserDoc(BaseModel):
    handle: str  # E.164 phone, iMessage email, or "web:<uuid>"
    channel: Channel
    lang: str | None = None  # ISO 639-1, e.g. "en", "es"
    zip: str | None = None
    subscribed: bool = False
    photon_space_id: str | None = None
    photon_agent_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageDoc(BaseModel):
    handle: str
    direction: Literal["in", "out"]
    body: str
    zip: str | None = None
    location: GeoPoint | None = None  # set when the user's location is known (feeds the live map)
    channel: Channel
    photon_message_id: str | None = None
    created_at: datetime


class PhotonMeta(BaseModel):
    space_id: str  # incoming message space.id
    agent_id: str  # incoming message receivedBy.id
    message_id: str  # incoming message id


class FindFoodArgs(BaseModel):
    zip: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    kind: PlaceKind | None = None
    accepts_snap: bool | None = None
    open_day: Day | None = None
    limit: int = 3


class ResolvedPoint(BaseModel):
    zip: str | None = None
    location: GeoPoint


class ReplyArgs(BaseModel):
    handle: str
    text: str
    channel: Channel
    photon: PhotonMeta | None = None
