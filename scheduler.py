"""Kyiv-time publishing schedule."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import PUBLISH_INTERVAL_MINUTES, PUBLISH_TIMES, SCHEDULE_MODE, TIMEZONE_NAME

logger = logging.getLogger(__name__)


def create_scheduler(publisher: object) -> AsyncIOScheduler:
    timezone = ZoneInfo(TIMEZONE_NAME)
    scheduler = AsyncIOScheduler(timezone=timezone)

    async def publish_daily(time_label: str) -> None:
        now = datetime.now(timezone)
        await publisher.publish(
            origin="scheduled",
            schedule_key=f"daily:{now.date().isoformat()}:{time_label}",
        )

    async def publish_interval() -> None:
        now = datetime.now(timezone)
        interval_seconds = PUBLISH_INTERVAL_MINUTES * 60
        slot = int(now.timestamp() // interval_seconds)
        await publisher.publish(origin="scheduled", schedule_key=f"interval:{slot}")

    if SCHEDULE_MODE == "daily":
        if not PUBLISH_TIMES:
            raise ValueError("PUBLISH_TIMES must contain at least one HH:MM value")
        for time_label in PUBLISH_TIMES:
            try:
                hour, minute = (int(part) for part in time_label.split(":"))
                if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                    raise ValueError
            except ValueError as exc:
                raise ValueError(f"Invalid PUBLISH_TIMES entry: {time_label!r}") from exc
            scheduler.add_job(
                publish_daily,
                CronTrigger(hour=hour, minute=minute, timezone=timezone),
                kwargs={"time_label": f"{hour:02d}:{minute:02d}"},
                id=f"daily-{hour:02d}-{minute:02d}",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=300,
            )
    elif SCHEDULE_MODE == "interval":
        if PUBLISH_INTERVAL_MINUTES <= 0:
            raise ValueError("PUBLISH_INTERVAL_MINUTES must be positive")
        scheduler.add_job(
            publish_interval,
            "interval",
            minutes=PUBLISH_INTERVAL_MINUTES,
            timezone=timezone,
            next_run_time=datetime.now(timezone) + timedelta(minutes=PUBLISH_INTERVAL_MINUTES),
            id="interval-publish",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )
    else:
        raise ValueError("SCHEDULE_MODE must be 'daily' or 'interval'")

    logger.info("Configured %s publishing schedule in %s", SCHEDULE_MODE, TIMEZONE_NAME)
    return scheduler

