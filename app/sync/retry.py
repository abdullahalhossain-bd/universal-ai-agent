"""Retry/backoff policy for durable sync jobs."""
from __future__ import annotations

import random

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 1800


def retry_delay(attempt: int) -> int:
    """Exponential backoff with jitter; attempt is 1-based."""
    exponent = max(0, attempt - 1)
    return min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2 ** exponent)) + random.randint(0, 15)
