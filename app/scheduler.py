from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.service import AccountabilityService
from app.telegram_client import TelegramClient

SGT = ZoneInfo("Asia/Singapore")


def build_scheduler(service: AccountabilityService, telegram: TelegramClient) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=SGT)

    def send_to_latest_chat(text: str | None) -> None:
        if not text:
            return
        chat_id = service.db.latest_chat_id()
        if chat_id is not None:
            telegram.send_message_sync(chat_id, text)

    scheduler.add_job(
        lambda: send_to_latest_chat(service.morning_reminder()),
        CronTrigger(hour=8, minute=0, timezone=SGT),
        id="morning-goal-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_latest_chat(service.missing_goals_reminder()),
        CronTrigger(hour=9, minute=30, timezone=SGT),
        id="missing-goals-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_latest_chat(service.completion_reminder()),
        CronTrigger(hour=22, minute=0, timezone=SGT),
        id="completion-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_latest_chat(service.close_day_summary(datetime.now(SGT).date() - timedelta(days=1))),
        CronTrigger(hour=5, minute=0, timezone=SGT),
        id="daily-close",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_latest_chat(service.month_score()),
        CronTrigger(day="last", hour=21, minute=0, timezone=SGT),
        id="monthly-summary",
        replace_existing=True,
    )
    return scheduler
