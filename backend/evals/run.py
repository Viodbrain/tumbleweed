"""Runs the 15 eval cases through reply(). Usage, from backend/: uv run python -m evals.run

Needs ANTHROPIC_API_KEY and MONGODB_URI (B's Atlas, or a local mongo:7), loaded via app.config.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from app.config import load_environment

HERE = Path(__file__).parent
load_environment()

PLACEHOLDERS = {
    "{RURAL_ZIP}": os.getenv("EVAL_RURAL_ZIP", "99344"),
    "{RURAL_TOWN}": os.getenv("EVAL_RURAL_TOWN", "Othello"),
    # Seattle data isn't loaded yet; set EVAL_SEATTLE_ZIP=98101 once it is.
    "{SEATTLE_ZIP}": os.getenv("EVAL_SEATTLE_ZIP", "99344"),
}
EMOJI = re.compile("[\U0001f000-\U0001faff⌀-⏿☀-➿⬀-⯿]")
MARKDOWN = re.compile(r"\*\*|__|^\s*[-*•]\s", re.MULTILINE)


def fill(text: str) -> str:
    for key, value in PLACEHOLDERS.items():
        text = text.replace(key, value)
    return text


def names_in(results: list[dict[str, Any]]) -> set[str]:
    out = set()
    for r in results:
        for key in ("name", "place_name", "title"):
            if r.get(key):
                out.add(r[key])
    return out


def check_case(case, replies, langs, tool_results, known_places) -> list[str]:
    problems = []
    allowed = {n.lower() for n in names_in(tool_results)}
    for text in replies:
        if len(text) > 300:
            problems.append(f"{len(text)} chars")
        if EMOJI.search(text):
            problems.append("emoji")
        if MARKDOWN.search(text):
            problems.append("markdown")
        lowered = text.lower()
        for name in known_places:
            if name.lower() in lowered and name.lower() not in allowed:
                problems.append(f"place not from tools: {name}")
    if langs[-1] != case["expect_lang"]:
        problems.append(f"lang {langs[-1]} != {case['expect_lang']}")
    final = replies[-1].lower()
    if case.get("expect_places") and not tool_results:
        problems.append("no tool results")
    if case.get("expect_no_tools") and tool_results:
        problems.append("unexpected tool call")
    for s in case.get("expect_contains", []):
        if s.lower() not in final:
            problems.append(f"missing '{s}'")
    if case.get("expect_any") and not any(s in final for s in case["expect_any"]):
        problems.append(f"missing any of {case['expect_any']}")
    if case.get("expect_official_link"):
        from app.prompt import OFFICIAL_URLS

        if not any(
            u.split("://", 1)[1].removeprefix("www.") in final for u in OFFICIAL_URLS
        ):
            problems.append("no official link")
    return problems


async def main() -> int:
    missing = [k for k in ("ANTHROPIC_API_KEY", "MONGODB_URI") if not os.getenv(k)]
    if missing:
        print(f"evals not run: missing {', '.join(missing)} (set them in backend/.env)")
        return 2

    from app import brain
    from app.db import get_db
    from app.models import ReplyArgs

    db = get_db()
    await db.users.delete_many({"handle": {"$regex": "^eval:"}})
    await db.messages.delete_many({"handle": {"$regex": "^eval:"}})
    known_places = {d["name"] async for d in db.places.find({}, {"name": 1})}

    cases = json.loads((HERE / "cases.json").read_text())
    rows, latencies, results = [], [], []
    for case in cases:
        handle = f"eval:{case['id']}"
        replies, langs, tool_results = [], [], []
        for turn in case["turns"]:
            start = time.perf_counter()
            text = await brain.reply(
                ReplyArgs(handle=handle, text=fill(turn), channel="web")
            )
            latencies.append((time.perf_counter() - start) * 1000)
            tool_results.extend(brain.last_tool_results)
            user = await db.users.find_one({"handle": handle})
            replies.append(text)
            langs.append((user or {}).get("lang"))
        results.append((case, replies, langs, tool_results))
        known_places |= names_in(tool_results)

    # Check after the run, so a place returned in any case counts as a known name.
    passed = 0
    for (case, replies, langs, tool_results), ms in zip(
        results, _per_case_ms(cases, latencies), strict=True
    ):
        problems = check_case(case, replies, langs, tool_results, known_places)
        passed += not problems
        rows.append(
            (
                case["id"],
                case["name"],
                replies[-1],
                len(replies[-1]),
                langs[-1],
                ms,
                problems,
            )
        )

    for cid, name, text, chars, lang, ms, problems in rows:
        status = "PASS" if not problems else "FAIL: " + "; ".join(problems)
        print(f"\n#{cid} {name} | {chars} chars | lang={lang} | {ms:.0f} ms | {status}")
        print("   " + text.replace("\n", "\n   "))

    q = statistics.quantiles(latencies, n=20)
    print(
        f"\n{passed}/{len(cases)} passed | p50 {statistics.median(latencies):.0f} ms | p95 {q[18]:.0f} ms"
    )
    return 0 if passed == len(cases) else 1


def _per_case_ms(cases, latencies):
    i = 0
    for case in cases:
        n = len(case["turns"])
        yield latencies[i + n - 1]
        i += n


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
