"""reply() pipeline tests with an in-memory Mongo and a scripted model: no Atlas, no LLM."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app import brain, user_context
from app.models import GeoPoint, MessageDoc, PhotonMeta, PlaceResult, ReplyArgs, ResolvedPoint, UserDoc

OTHELLO = GeoPoint(coordinates=(-119.17, 46.82))


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction):
        self.rows.sort(key=lambda r: r[key], reverse=direction < 0)
        return self

    async def to_list(self, limit):
        return deepcopy(self.rows[:limit])


class Collection:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 0

    @staticmethod
    def _matches(row, query):
        return all(
            row.get(k) != v["$ne"] if isinstance(v, dict) else row.get(k) == v for k, v in query.items()
        )

    async def find_one(self, query):
        return next((deepcopy(r) for r in self.rows if self._matches(r, query)), None)

    async def update_one(self, query, update, upsert=False):
        row = next((r for r in self.rows if self._matches(r, query)), None)
        if row is None:
            if not upsert:
                return
            row = deepcopy(query) | deepcopy(update.get("$setOnInsert", {}))
            self.rows.append(row)
        row.update(deepcopy(update.get("$set", {})))

    async def find_one_and_update(self, query, update, upsert=False, **_):
        await self.update_one(query, update, upsert=upsert)
        return await self.find_one(query)

    async def insert_one(self, row):
        self.next_id += 1
        self.rows.append(deepcopy(row) | {"_id": self.next_id})
        return SimpleNamespace(inserted_id=self.next_id)

    def find(self, query):
        return Cursor([deepcopy(r) for r in self.rows if self._matches(r, query)])

    async def delete_one(self, query):
        row = next((r for r in self.rows if self._matches(r, query)), None)
        if row is not None:
            self.rows.remove(row)

    async def delete_many(self, query):
        self.rows = [r for r in self.rows if not self._matches(r, query)]


def place(name="Othello Food Bank", distance=0.7) -> PlaceResult:
    return PlaceResult.model_validate(
        {
            "_id": name.lower().replace(" ", "-"),
            "name": name,
            "kind": "foodbank",
            "address": "949 E Main St, Othello, WA",
            "location": OTHELLO,
            "hours": "Mon-Wed 1pm-4pm",
            "region": "rural",
            "distance_mi": distance,
        }
    )


class Model:
    """Scripted stand-in for call_model: each step is a function of the messages so far."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls: list[dict] = []

    async def __call__(self, system, messages, tool_choice, max_tokens=600):
        self.calls.append({"system": system, "messages": deepcopy(messages), "choice": tool_choice})
        step = self.steps.pop(0)
        out = step(messages) if callable(step) else step
        if isinstance(out, BaseException):
            raise out
        return out


def use(name, **inp):
    return [{"type": "tool_use", "id": f"toolu_{name}_{len(json.dumps(inp))}", "name": name, "input": inp}]


def say(text, lang="en", zip=None):
    return use("send_reply", lang=lang, text=text, zip=zip)


@pytest.fixture
def db(monkeypatch):
    database = SimpleNamespace(users=Collection(), messages=Collection(), user_context=Collection())
    monkeypatch.setattr(brain, "get_db", lambda: database)
    monkeypatch.setattr(user_context, "get_db", lambda: database)

    async def resolve_point(zip=None, city=None):
        return ResolvedPoint(zip=zip, location=OTHELLO) if zip == "99344" else None

    async def find_food(args):
        return [place(), place("Walmart Supercenter #3217", 1.3)] if args.zip == "99344" else []

    monkeypatch.setattr(brain.data, "resolve_point", resolve_point)
    monkeypatch.setattr(brain.data, "find_food", find_food)
    return database


def model(monkeypatch, *steps) -> Model:
    m = Model(*steps)
    monkeypatch.setattr(brain, "call_model", m)
    return m


async def send(text, handle="+15095550100", channel="sms", photon=None):
    return await brain.reply(ReplyArgs(handle=handle, text=text, channel=channel, photon=photon))


def user(db, handle="+15095550100"):
    return next(r for r in db.users.rows if r["handle"] == handle)


# ---------- keywords ----------


async def test_join_and_stop_toggle_subscription_without_the_model(db, monkeypatch):
    m = model(monkeypatch)
    assert await send("join") == brain.JOIN_REPLY
    assert user(db)["subscribed"] is True
    assert await send(" Stop. ") == brain.STOP_REPLY
    assert user(db)["subscribed"] is False
    assert await send("HELP!") == brain.HELP_REPLY
    assert m.calls == []
    assert [r["direction"] for r in db.messages.rows] == ["in", "out"] * 3


async def test_empty_message_gets_help(db, monkeypatch):
    model(monkeypatch)
    assert await send("   ") == brain.HELP_REPLY


# ---------- fast path ----------


async def test_fast_path_saves_zip_and_puts_pins_on_both_messages(db, monkeypatch):
    m = model(monkeypatch)
    out = await send("99344")
    assert out.startswith("Food near 99344 (miles from town center):\n1. Othello Food Bank, 0.7 mi")
    assert m.calls == []
    u = user(db)
    assert (u["zip"], u["lang"]) == ("99344", "en")
    inbound, outbound = db.messages.rows
    assert inbound["zip"] == "99344" and inbound["location"] is not None  # backfilled
    assert outbound["location"] is not None


async def test_unknown_zip_is_not_saved(db, monkeypatch):
    model(monkeypatch)
    out = await send("00000")
    assert "2-1-1" in out
    assert user(db)["zip"] is None
    assert all(r["location"] is None for r in db.messages.rows)


# ---------- LLM path ----------


async def test_llm_search_then_reply_saves_lang_zip_and_location(db, monkeypatch):
    def answer(messages):
        found = json.loads(messages[-1]["content"][0]["content"])["results"]
        return say(f"1. {found[0]['name']}, about {found[0]['distance_mi']} mi", lang="es", zip="99344")

    m = model(monkeypatch, use("find_food", zip="99344", open_day="sat"), answer)
    out = await send("necesito comida hoy cerca de 99344")
    assert out == "1. Othello Food Bank, about 0.7 mi"
    assert [c["choice"]["type"] for c in m.calls] == ["any", "any"]
    assert "Today is" in m.calls[0]["system"]
    u = user(db)
    assert (u["zip"], u["lang"]) == ("99344", "es")
    assert all(r["location"] is not None for r in db.messages.rows)
    assert brain.last_tool_results[0]["name"] == "Othello Food Bank"


async def test_memory_sends_prior_turns_and_known_zip(db, monkeypatch):
    model(monkeypatch)
    await send("99344")
    m = model(monkeypatch, say("I don't have bus data. Please call the food bank."))
    await send("which one is closest to the bus?")
    roles = [msg["role"] for msg in m.calls[0]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert "last known ZIP is 99344" in m.calls[0]["system"]


async def test_history_is_capped(db, monkeypatch):
    for i in range(5):
        model(monkeypatch, say(f"reply {i}"))
        await send(f"question {i}")
    m = model(monkeypatch, say("ok"))
    await send("one more")
    assert len(m.calls[0]["messages"]) == brain.HISTORY_MESSAGES + 1


async def test_spanish_user_bare_zip_goes_to_model(db, monkeypatch):
    model(monkeypatch, say("¿En qué le puedo ayudar?", lang="es"))
    await send("hola")
    m = model(monkeypatch, say("Comida cerca de 99344: ...", lang="es", zip="99344"))
    await send("99344")
    assert len(m.calls) == 1


async def test_photon_ids_and_channel_are_stored(db, monkeypatch):
    model(monkeypatch)
    meta = PhotonMeta(space_id="spc_1", agent_id="usr_agent", message_id="pho_msg_1")
    await send("99344", channel="imessage", photon=meta)
    u = user(db)
    assert (u["photon_space_id"], u["photon_agent_id"], u["channel"]) == ("spc_1", "usr_agent", "imessage")
    assert db.messages.rows[0]["photon_message_id"] == "pho_msg_1"


async def test_stored_docs_match_the_shared_models(db, monkeypatch):
    model(monkeypatch)
    await send("99344")
    model(monkeypatch, say("Hi"))
    await send("hello")
    for r in db.messages.rows:
        MessageDoc.model_validate(r)
    for r in db.users.rows:
        UserDoc.model_validate(r)


# ---------- failure modes: every one must return a valid string <= 300 chars ----------


async def test_model_outage_returns_fallback_and_keeps_inbound(db, monkeypatch):
    model(monkeypatch, RuntimeError("anthropic down"))
    assert await send("food please") == brain.ERROR_REPLY
    assert [r["direction"] for r in db.messages.rows] == ["in"]


async def test_slow_model_hits_the_deadline(db, monkeypatch):
    async def slow_model(system, messages, tool_choice, max_tokens=600):
        await asyncio.sleep(5)

    monkeypatch.setattr(brain, "call_model", slow_model)
    monkeypatch.setattr(brain, "REPLY_DEADLINE_S", 0.05)
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await send("food please") == brain.ERROR_REPLY
    assert loop.time() - started < 1


async def test_model_without_tool_call_returns_fallback(db, monkeypatch):
    model(monkeypatch, [{"type": "text", "text": "Here is some food info"}])
    assert await send("food please") == brain.ERROR_REPLY


async def test_unknown_tool_is_reported_back_then_reply(db, monkeypatch):
    def check(messages):
        result = messages[-1]["content"][0]
        assert result["is_error"] is True and "Unknown tool" in result["content"]
        return say("What is your ZIP code?")

    model(monkeypatch, use("search_web", q="food"), check)
    assert await send("food please") == "What is your ZIP code?"


async def test_overlong_reply_is_cut_to_300(db, monkeypatch):
    long = "This is a long sentence about food. " * 20
    model(monkeypatch, say(long), say(long))  # first answer, then the one shorten retry
    out = await send("tell me everything")
    assert len(out) <= 300 and out.endswith(".")


async def test_very_long_input_is_truncated_for_the_model(db, monkeypatch):
    m = model(monkeypatch, say("Please send a shorter message with your ZIP code."))
    out = await send("food " * 2000)
    assert len(m.calls[0]["messages"][-1]["content"]) <= brain.MAX_INPUT_CHARS
    assert len(out) <= 300


async def test_emoji_and_markdown_from_the_model_are_stripped(db, monkeypatch):
    model(monkeypatch, say("**Othello Food Bank** \U0001f34e\n- open Mon-Wed"))
    out = await send("\U0001f37d\U0001f37d")
    assert out == "Othello Food Bank\nopen Mon-Wed"
