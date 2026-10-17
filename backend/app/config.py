"""One environment loader: process > backend/.env > legacy root .env.local."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_config() -> dict[str, str]:
    values = {
        **dotenv_values(ROOT / ".env.local", interpolate=False),
        **dotenv_values(ROOT / "backend/.env", interpolate=False),
        **os.environ,
    }
    return {key: value for key, value in values.items() if value is not None}


def load_environment() -> None:
    """Expose the same configuration to existing getenv-based integrations."""
    for key, value in get_config().items():
        os.environ.setdefault(key, value)
