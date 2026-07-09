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

    def send_to_all_active_chats(factory) -> None:
        for chat_id in service.db.active_chat_ids():
            text = factory(chat_id)
            if text:
                telegram.send_message_sync(chat_id, text)

    scheduler.add_job(
        lambda: send_to_all_active_chats(lambda chat_id: service.morning_reminder()),
        CronTrigger(hour=8, minute=0, timezone=SGT),
        id="morning-goal-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats(lambda chat_id: service.missing_goals_reminder(chat_id=chat_id)),
        CronTrigger(hour=9, minute=30, timezone=SGT),
        id="missing-goals-reminder",
        replace_existing=True,
    )
    for hour in (20, 22):
        scheduler.add_job(
            lambda: send_to_all_active_chats(lambda chat_id: service.completion_reminder(chat_id=chat_id)),
            CronTrigger(hour=hour, minute=0, timezone=SGT),
            id=f"completion-reminder-{hour}",
            replace_existing=True,
        )
    scheduler.add_job(
        lambda: send_to_all_active_chats(
            lambda chat_id: service.close_day_summary(chat_id=chat_id, checkin_date=datetime.now(SGT).date() - timedelta(days=1))
        ),
        CronTrigger(hour=5, minute=0, timezone=SGT),
        id="daily-close",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats(lambda chat_id: service.month_score(chat_id=chat_id)),
        CronTrigger(day="last", hour=21, minute=0, timezone=SGT),
        id="monthly-summary",
        replace_existing=True,
    )
    return scheduler
