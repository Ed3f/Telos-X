"""Small scheduling helpers retained for compatibility."""

from datetime import datetime, timedelta


def scheduled_message(h: int, m: int) -> float:
    """Return seconds until the next occurrence of ``h:m`` local time."""
    if not 0 <= h <= 23 or not 0 <= m <= 59:
        raise ValueError("hour must be 0..23 and minute must be 0..59")

    now = datetime.now()
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()



