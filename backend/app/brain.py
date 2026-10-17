"""Owner: C. STUB -- replace the body, never the signature."""

from __future__ import annotations

from app.models import ReplyArgs


async def reply(args: ReplyArgs) -> str:
    return f'Tumbleweed stub. You said: "{args.text[:200]}"'
