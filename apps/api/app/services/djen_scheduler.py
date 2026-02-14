"""
Helpers para cálculo de próximo sync de watchlists DJEN/DataJud.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def compute_next_sync(
    frequency: str,
    sync_time: str,
    timezone: str = "America/Sao_Paulo",
    cron: str | None = None,
) -> datetime:
    """Compute the next sync datetime in UTC based on user-configured schedule.

    Args:
        frequency: daily, twice_daily, weekly, custom
        sync_time: HH:MM in user's timezone
        timezone: User's timezone string
        cron: Custom cron expression (only when frequency='custom')

    Returns:
        Next sync datetime in UTC.
    """
    tz = ZoneInfo(timezone)
    now_local = datetime.now(tz)

    hour, minute = (int(x) for x in sync_time.split(":"))

    if frequency == "daily":
        candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now_local:
            candidate += timedelta(days=1)
        return candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    elif frequency == "twice_daily":
        # Two syncs: at sync_time and 12 hours later
        first = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        second = first + timedelta(hours=12)

        candidates = [first, second]
        # Also consider tomorrow's first
        candidates.append(first + timedelta(days=1))

        future = [c for c in candidates if c > now_local]
        next_sync = min(future) if future else first + timedelta(days=1)
        return next_sync.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    elif frequency == "weekly":
        # Sync once a week on the same weekday as creation, at sync_time
        candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now_local:
            candidate += timedelta(days=7)
        return candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    elif frequency == "custom" and cron:
        # Parse simple cron: "minute hour day_of_month month day_of_week"
        try:
            from croniter import croniter
            cron_iter = croniter(cron, now_local)
            next_dt = cron_iter.get_next(datetime)
            return next_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        except ImportError:
            # Fallback: treat as daily if croniter not available
            candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now_local:
                candidate += timedelta(days=1)
            return candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    # Default: tomorrow at sync_time
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)
    return candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
