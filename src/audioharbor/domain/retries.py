import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def retry_after(value: str | None, now: datetime | None = None) -> float | None:
    if not value: return None
    try: return max(0.0, float(value))
    except ValueError: pass
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None: date = date.replace(tzinfo=UTC)
        return max(0.0, (date - (now or datetime.now(UTC))).total_seconds())
    except (TypeError, ValueError, OverflowError): return None

def backoff(attempt: int, rng=random.random) -> float:
    return rng() * min(120.0, 2.0 * (2 ** max(0, attempt - 1)))

