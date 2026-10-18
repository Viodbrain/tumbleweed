"""Bounded, self-reported preferences scoped to the caller's existing handle."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db import get_db

FoodPreference = Literal[
    "vegetarian",
    "vegan",
    "halal",
    "kosher",
    "no_pork",
    "no_beef",
    "no_seafood",
    "no_preference",
]


class ContextPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    food_preferences: list[FoodPreference] = Field(default_factory=list, max_length=8)


async def load_context(handle: str) -> dict:
    row = await get_db().user_context.find_one({"_id": handle})
    if row is None:
        return {}
    # Only allowlisted fields reach the model, never identifiers or arbitrary text.
    fields = {key: row[key] for key in ContextPatch.model_fields if key in row}
    context = ContextPatch.model_validate(fields).model_dump(exclude_unset=True, exclude_none=True)
    return {key: value for key, value in context.items() if value != []}


async def save_context(handle: str, updates: dict) -> dict:
    patch = ContextPatch.model_validate(updates).model_dump(exclude_unset=True)
    if not patch:
        raise ValueError("At least one context field is required")
    if "food_preferences" in patch:
        patch["food_preferences"] = list(dict.fromkeys(patch["food_preferences"]))
    now = datetime.now(UTC)
    await get_db().user_context.update_one(
        {"_id": handle},
        {"$set": {**patch, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return patch


async def forget_context(handle: str) -> None:
    """Clear conversational context, retaining the account/subscription identity."""
    db = get_db()
    await db.user_context.delete_one({"_id": handle})
    await db.messages.delete_many({"handle": handle})
    await db.users.update_one(
        {"handle": handle},
        {"$set": {"zip": None, "lang": None, "updated_at": datetime.now(UTC)}},
    )
