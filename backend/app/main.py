"""Owner: A. FastAPI entry point: `uv run uvicorn app.main:app --reload`."""

from __future__ import annotations

import logging
import os

from app.config import load_environment

load_environment()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.routes import demo, photon  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Tumbleweed API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(photon.router)
app.include_router(demo.router)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}
