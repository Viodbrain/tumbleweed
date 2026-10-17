"""Deterministic brain tests: no LLM, no network, no database."""

from datetime import UTC, datetime

import pytest

from app import brain
from app.brain import (
    ERROR_REPLY,
    HELP_REPLY,
    JOIN_REPLY,
    STOP_REPLY,
    clean_text,
    enforce_length,
    fast_path_reply,
    is_zip_only,
    parse_keyword,
)
from app.models import GeoPoint, PlaceResult
from app.prompt import OFFICIAL_URLS, system_prompt

EMOJI = "\U0001f34e"


def place(**overrides) -> PlaceResult:
    base = {
        "_id": "hope-pantry-omak",
        "name": "Hope Pantry",
        "kind": "foodbank",
        "address": "1 Main St, Omak, WA",
        "location": GeoPoint(coordinates=(-119.5, 48.4)),
        "hours": "Tue/Thu 10am-2pm",
        "days": ["tue", "thu"],
        "region": "rural",
        "distance_mi": 1.234,
    }
    return PlaceResult.model_validate(base | overrides)


# ---------- keywords ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("join", "JOIN"),
        (" Stop. ", "STOP"),
        ("help!", "HELP"),
        ("HELP?\n", "HELP"),
        ("JoIn", "JOIN"),
    ],
)
def test_keywords_match_whole_message(text, expected):
    assert parse_keyword(text) == expected


@pytest.mark.parametrize(
    "text",
    ["join us tomorrow", "stop by the pantry", "I need help", "", "98101", "helpp"],
)
def test_non_keywords(text):
    assert parse_keyword(text) is None


def test_reply_strings_are_exact():
    assert (
        JOIN_REPLY
        == "You're signed up for food event reminders near you. Text STOP to opt out."
    )
    assert (
        STOP_REPLY == "You won't get reminders anymore. You can still text me anytime."
    )
    assert HELP_REPLY == (
        "Text your ZIP code or town to find free food, groceries that take SNAP, "
        "and farmers markets near you. Any language works."
    )
    assert (
        ERROR_REPLY
        == "Sorry, something went wrong on our end. Please try again, or text your ZIP code."
    )


# ---------- ZIP detection ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("98101", "98101"), ("  98101 \n", "98101"), ("00000", "00000")],
)
def test_zip_only(text, expected):
    assert is_zip_only(text) == expected


@pytest.mark.parametrize(
    "text", ["9810", "981011", "98101-1234", "zip 98101", "", "98101 please"]
)
def test_not_zip_only(text):
    assert is_zip_only(text) is None


# ---------- fast path ----------


def test_fast_path_no_places_suggests_211():
    r = fast_path_reply("00000", [])
    assert "40 miles" in r and "2-1-1" in r and "00000" in r
    assert len(r) <= 300


def test_fast_path_one_place():
    r = fast_path_reply("98841", [place()])
    assert r.startswith("Food near 98841 (miles from town center):\n1. Hope Pantry, 1.2 mi, Tue/Thu 10am-2pm")
    assert "\n2." not in r
    assert len(r) <= 300


def test_fast_path_lists_three_of_five_and_handles_missing_hours():
    places = [
        place(),
        place(name="Omak Market", distance_mi=2, hours=None, phone="509-555-0100"),
        place(name="Sunrise Meals", distance_mi=3.5, hours=None),
        place(name="Fourth", distance_mi=4),
        place(name="Fifth", distance_mi=5),
    ]
    r = fast_path_reply("98841", places)
    assert "\n1. Hope Pantry" in r
    assert "\n2. Omak Market, 2.0 mi, call 509-555-0100 for hours" in r
    assert "\n3. Sunrise Meals, 3.5 mi" in r
    assert "Fourth" not in r
    assert len(r) <= 300


def test_fast_path_long_names_stay_within_limit():
    long = "Community Emergency Food Assistance Network Distribution Center of the Greater Okanogan Valley"
    places = [
        place(
            name=f"{long} {n}",
            hours="Mon/Tue/Wed/Thu/Fri 9am-12pm and 1pm-5pm, Sat 10am-2pm",
            distance_mi=n,
        )
        for n in (1, 2, 3)
    ]
    r = fast_path_reply("98841", places)
    assert len(r) <= 300
    assert r.startswith("Food near 98841 (miles from town center):\n1. ")


def test_fast_path_strips_emojis_from_data():
    r = fast_path_reply(
        "98101", [place(name=f"Hope Pantry {EMOJI}", hours="Daily ⏰ 9-5")]
    )
    assert EMOJI not in r and "⏰" not in r
    assert "Hope Pantry, 1.2 mi" in r


# ---------- length guard ----------


def test_enforce_length_leaves_short_text_alone():
    assert enforce_length("Hello there.") == "Hello there."
    assert len(enforce_length("x" * 300)) == 300


def test_enforce_length_cuts_at_sentence_boundary():
    r = enforce_length("First sentence here. " + "Second sentence is long. " * 20)
    assert len(r) <= 300
    assert r.endswith(".")


def test_enforce_length_spanish_and_newlines():
    s = (
        "¿Necesitas comida hoy?\n1. Banco de Comida, 1.2 mi, mar 10-2\n2. "
        + "Mercado " * 40
    )
    r = enforce_length(s)
    assert len(r) <= 300
    assert r.endswith("mar 10-2")


def test_enforce_length_ignores_list_markers():
    r = enforce_length("Places:\n1. " + "word " * 80)
    assert len(r) <= 300
    assert r != "Places:\n1."


def test_enforce_length_hard_cut_drops_trailing_punctuation():
    r = enforce_length("word, " * 100)
    assert len(r) <= 300
    assert r.endswith("word")


def test_clean_text_removes_markdown_and_emojis():
    assert (
        clean_text(f"**Hope Pantry** {EMOJI}\n- open today")
        == "Hope Pantry\nopen today"
    )


# ---------- prompt ----------


def test_system_prompt_injects_date_and_weekday(monkeypatch):
    monkeypatch.setenv("DEFAULT_TZ", "America/Los_Angeles")
    # 18:00 UTC on 2026-10-17 is Saturday morning in Los Angeles.
    p = system_prompt(datetime(2026, 10, 17, 18, 0, tzinfo=UTC))
    assert "Saturday, October 17, 2026" in p
    assert '"today" = "sat"' in p and '"tomorrow" = "sun"' in p
    # 06:30 UTC on 2026-10-18 is still Saturday evening in Los Angeles.
    assert '"today" = "sat"' in system_prompt(datetime(2026, 10, 18, 6, 30, tzinfo=UTC))


def test_system_prompt_contains_every_official_link():
    p = system_prompt()
    for url in OFFICIAL_URLS:
        assert url in p


# ---------- tool loop with a fake model ----------


def _tool_use(name, inp, id_="t1"):
    return [{"type": "tool_use", "id": id_, "name": name, "input": inp}]


async def test_run_agent_searches_then_replies(monkeypatch):
    calls = []
    script = [
        _tool_use("find_food", {"zip": "98841", "open_day": "sat"}, "t1"),
        _tool_use(
            "send_reply",
            {"text": "1. Omak Food Bank, 0.2 mi", "lang": "EN", "zip": "98841"},
            "t2",
        ),
    ]

    async def fake_call_model(system, messages, tool_choice, max_tokens=600):
        calls.append(tool_choice)
        return script[len(calls) - 1]

    async def fake_find_food(args):
        assert args.zip == "98841" and args.open_day == "sat"
        return [place(name="Omak Food Bank", distance_mi=0.2)]

    monkeypatch.setattr(brain, "call_model", fake_call_model)
    monkeypatch.setattr(brain.data, "find_food", fake_find_food)
    brain.last_tool_results.clear()
    out = await brain.run_agent("sys", [{"role": "user", "content": "food 98841"}])
    assert out == {"text": "1. Omak Food Bank, 0.2 mi", "lang": "en", "zip": "98841"}
    assert [c["type"] for c in calls] == ["any", "any"]
    assert brain.last_tool_results[0]["name"] == "Omak Food Bank"


async def test_run_agent_forces_send_reply_after_three_rounds(monkeypatch):
    calls = []

    async def fake_call_model(system, messages, tool_choice, max_tokens=600):
        calls.append(tool_choice)
        if tool_choice["type"] == "tool":
            return _tool_use(
                "send_reply",
                {"text": "Sorry, nothing found.", "lang": "en", "zip": None},
                "final",
            )
        return _tool_use("find_food", {"city": "nowhere"}, f"t{len(calls)}")

    async def fake_find_food(args):
        return []

    monkeypatch.setattr(brain, "call_model", fake_call_model)
    monkeypatch.setattr(brain.data, "find_food", fake_find_food)
    out = await brain.run_agent("sys", [{"role": "user", "content": "food"}])
    assert out["text"] == "Sorry, nothing found."
    assert [c["type"] for c in calls] == ["any", "any", "any", "tool"]


async def test_run_agent_shortens_long_reply_once(monkeypatch):
    calls = []

    async def fake_call_model(system, messages, tool_choice, max_tokens=600):
        calls.append(tool_choice)
        text = "Long sentence here. " * 30 if len(calls) == 1 else "Short now."
        return _tool_use(
            "send_reply", {"text": text, "lang": "en", "zip": None}, f"t{len(calls)}"
        )

    monkeypatch.setattr(brain, "call_model", fake_call_model)
    out = await brain.run_agent("sys", [{"role": "user", "content": "hi"}])
    assert out["text"] == "Short now."
    assert len(calls) == 2


async def test_run_agent_reports_bad_tool_args_to_model(monkeypatch):
    seen = []

    async def fake_call_model(system, messages, tool_choice, max_tokens=600):
        if len(seen) == 0:
            seen.append(1)
            return _tool_use("find_food", {"open_day": "someday"}, "t1")
        seen.append(messages[-1]["content"][0])
        return _tool_use(
            "send_reply",
            {"text": "What is your ZIP code?", "lang": "en", "zip": "abc"},
            "t2",
        )

    monkeypatch.setattr(brain, "call_model", fake_call_model)
    out = await brain.run_agent("sys", [{"role": "user", "content": "food"}])
    assert seen[1]["is_error"] is True
    assert out["zip"] is None


def test_history_alternates_roles_and_drops_leading_assistant():
    docs = [
        {"direction": "out", "body": "old bot reply"},
        {"direction": "in", "body": "need food 98841"},
        {"direction": "in", "body": "hello?"},
        {"direction": "out", "body": "1. Omak Food Bank"},
    ]
    msgs = brain._history_to_messages(docs, "which one is closest?")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "need food 98841\nhello?"
    assert msgs[-1]["content"] == "which one is closest?"
