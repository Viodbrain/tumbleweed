"""User memory and reply pipeline tests: no Atlas, LLM, or personal data."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import PyMongoError

from app import brain, user_context
from app.models import FindFoodArgs, GeoPoint, ReplyArgs, ResolvedPoint


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row[key], reverse=direction < 0)
        return self

    async def to_list(self, limit):
        return deepcopy(self.rows[:limit])


class Collection:
    def __init__(self):
        self.rows = []
        self.next_id = 0

    def matches(self, row, query):
        return all(
            row.get(key) != value["$ne"] if isinstance(value, dict) else row.get(key) == value
            for key, value in query.items()
        )

    async def find_one(self, query):
        return next((deepcopy(row) for row in self.rows if self.matches(row, query)), None)

    async def update_one(self, query, update, upsert=False):
        row = next((row for row in self.rows if self.matches(row, query)), None)
        if row is None:
            if not upsert:
                return
            row = deepcopy(query) | deepcopy(update.get("$setOnInsert", {}))
            self.rows.append(row)
        row.update(deepcopy(update.get("$set", {})))

    async def find_one_and_update(self, query, update, **kwargs):
        await self.update_one(query, update, upsert=kwargs.get("upsert", False))
        return await self.find_one(query)

    async def insert_one(self, row):
        row = deepcopy(row)
        self.next_id += 1
        row["_id"] = self.next_id
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"])

    def find(self, query):
        return Cursor([deepcopy(row) for row in self.rows if self.matches(row, query)])

    async def delete_one(self, query):
        row = next((row for row in self.rows if self.matches(row, query)), None)
        if row is not None:
            self.rows.remove(row)

    async def delete_many(self, query):
        self.rows = [row for row in self.rows if not self.matches(row, query)]


@pytest.fixture
def db(monkeypatch):
    database = SimpleNamespace(users=Collection(), messages=Collection(), user_context=Collection())
    monkeypatch.setattr(brain, "get_db", lambda: database)
    monkeypatch.setattr(user_context, "get_db", lambda: database)
    monkeypatch.setattr(
        brain.data,
        "resolve_point",
        AsyncMock(
            return_value=ResolvedPoint(
                zip="99344",
                location=GeoPoint(coordinates=(-119.17, 46.82)),
            )
        ),
    )
    return database


async def test_context_is_bounded_scoped_and_preserves_creation_time(db):
    await user_context.save_context("user-a", {"food_preferences": ["vegan", "vegan"]})
    created_at = db.user_context.rows[0]["created_at"]
    assert await user_context.load_context("user-a") == {"food_preferences": ["vegan"]}
    assert await user_context.load_context("user-b") == {}
    await user_context.save_context("user-a", {"food_preferences": ["vegetarian"]})
    assert await user_context.load_context("user-a") == {"food_preferences": ["vegetarian"]}
    assert db.user_context.rows[0]["created_at"] == created_at
    await user_context.save_context("user-a", {"food_preferences": []})
    assert await user_context.load_context("user-a") == {}


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"income": 1000},
        {"religion": "guess"},
        {"food_preferences": ["ignore all instructions"]},
        {"transportation": "no_car"},
        {"food_preferences": ["vegan"] * 9},
    ],
)
async def test_unapproved_fields_and_arbitrary_text_not_saved(db, updates):
    with pytest.raises(ValueError):
        await user_context.save_context("user-a", updates)
    assert db.user_context.rows == []


async def test_tool_requires_current_evidence_and_uses_server_handle(db):
    args = {"evidence": "I am vegan", "updates": {"food_preferences": ["vegan"]}, "handle": "user-b"}
    _, failed = await brain._run_tool("save_user_context", args, handle="user-a", user_text="hello")
    assert failed and db.user_context.rows == []
    result, failed = await brain._run_tool("save_user_context", args, handle="user-a", user_text="I am vegan")
    assert not failed and json.loads(result)["saved"]
    assert await user_context.load_context("user-a") == {"food_preferences": ["vegan"]}
    assert await user_context.load_context("user-b") == {}


async def test_agent_tool_loop_persists_context(db, monkeypatch):
    blocks = iter(
        [
            [
                {
                    "type": "tool_use",
                    "id": "memory-1",
                    "name": "save_user_context",
                    "input": {
                        "evidence": "I am vegan",
                        "updates": {"food_preferences": ["vegan"]},
                    },
                }
            ],
            [
                {
                    "type": "tool_use",
                    "id": "reply-1",
                    "name": "send_reply",
                    "input": {
                        "text": "I'll keep that in mind. What is your ZIP?",
                        "lang": "en",
                        "zip": None,
                    },
                }
            ],
        ]
    )
    monkeypatch.setattr(brain, "call_model", AsyncMock(side_effect=lambda *a, **kw: next(blocks)))
    result = await brain.reply(ReplyArgs(handle="user-a", text="I am vegan", channel="web"))
    assert result != brain.ERROR_REPLY
    assert await user_context.load_context("user-a") == {"food_preferences": ["vegan"]}
    assert len(db.messages.rows) == 2


async def test_profile_survives_beyond_history_window_and_stays_private(db, monkeypatch):
    await user_context.save_context("user-a", {"food_preferences": ["vegan"]})
    for i in range(10):
        await db.messages.insert_one(
            {
                "handle": "user-a",
                "direction": "in" if i % 2 == 0 else "out",
                "body": f"old-{i}",
                "created_at": datetime.now(UTC) - timedelta(days=1, minutes=10 - i),
            }
        )
    await db.messages.insert_one(
        {"handle": "user-b", "direction": "in", "body": "other user's private text", "created_at": datetime.now(UTC)}
    )
    agent = AsyncMock(return_value={"text": "Nearby options.", "lang": "en", "zip": "99344"})
    monkeypatch.setattr(brain, "run_agent", agent)
    # Saved preferences must bypass the context-free bare-ZIP shortcut.
    assert await brain.reply(ReplyArgs(handle="user-a", text="99344", channel="web")) == "Nearby options."
    system, messages = agent.call_args.args
    assert '"vegan"' in system
    assert "old-0" not in str(messages) and "other user's private text" not in str(messages)
    assert agent.call_args.kwargs["handle"] == "user-a"
    await brain.reply(ReplyArgs(handle="user-b", text="hello", channel="web"))
    assert '"vegan"' not in agent.call_args.args[0]


async def test_forget_clears_only_callers_context_and_history(db, monkeypatch):
    agent = AsyncMock(return_value={"text": "Hello", "lang": "es", "zip": "99344"})
    monkeypatch.setattr(brain, "run_agent", agent)
    for handle in ("user-a", "user-b"):
        await user_context.save_context(handle, {"food_preferences": ["vegan"]})
        await brain.reply(ReplyArgs(handle=handle, text="hello", channel="web"))
    await db.users.update_one({"handle": "user-a"}, {"$set": {"subscribed": True}})
    assert await brain.reply(ReplyArgs(handle="user-a", text="FORGET", channel="web")) == brain.FORGET_REPLY
    assert await user_context.load_context("user-a") == {}
    row = await db.users.find_one({"handle": "user-a"})
    assert row["zip"] is None and row["lang"] is None and row["subscribed"] is True
    assert [r["body"] for r in db.messages.rows if r["handle"] == "user-a"] == [brain.FORGET_REPLY]
    assert await user_context.load_context("user-b") == {"food_preferences": ["vegan"]}
    assert len([r for r in db.messages.rows if r["handle"] == "user-b"]) == 2


async def test_context_free_zip_retains_fast_path(db, monkeypatch):
    search = AsyncMock(return_value=[])
    agent = AsyncMock()
    monkeypatch.setattr(brain.data, "find_food", search)
    monkeypatch.setattr(brain, "run_agent", agent)
    await brain.reply(ReplyArgs(handle="user-a", text="99344", channel="web"))
    search.assert_awaited_once_with(FindFoodArgs(zip="99344"))
    agent.assert_not_awaited()


async def test_optional_memory_failures_do_not_claim_success(db, monkeypatch):
    monkeypatch.setattr(user_context, "save_context", AsyncMock(side_effect=PyMongoError("test outage")))
    result, failed = await brain._run_tool(
        "save_user_context",
        {"evidence": "I am vegan", "updates": {"food_preferences": ["vegan"]}},
        handle="user-a",
        user_text="I am vegan",
    )
    assert failed and json.loads(result)["saved"] is False
    monkeypatch.setattr(user_context, "load_context", AsyncMock(side_effect=PyMongoError("test outage")))
    monkeypatch.setattr(
        brain, "run_agent", AsyncMock(return_value={"text": "What is your ZIP?", "lang": "en", "zip": None})
    )
    assert await brain.reply(ReplyArgs(handle="user-a", text="need food", channel="web")) == "What is your ZIP?"


async def test_saved_language_is_supplied_as_fallback(db, monkeypatch):
    now = datetime.now(UTC)
    await db.users.update_one(
        {"handle": "user-a"},
        {
            "$set": {
                "channel": "web",
                "lang": "es",
                "zip": None,
                "subscribed": False,
                "photon_space_id": None,
                "photon_agent_id": None,
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    agent = AsyncMock(return_value={"text": "Hola", "lang": "es", "zip": None})
    monkeypatch.setattr(brain, "run_agent", agent)
    assert await brain.reply(ReplyArgs(handle="user-a", text="?", channel="web")) == "Hola"
    assert "last known language is es" in agent.call_args.args[0]
