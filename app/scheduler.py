from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.service import AccountabilityService
from app.telegram_client import TelegramClient

SGT = ZoneInfo("Asia/Singapore")
logger = logging.getLogger(__name__)


def build_scheduler(service: AccountabilityService, telegram: TelegramClient) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=SGT)

    def send_to_all_active_chats(kind, factory, notification_date_factory=None) -> None:
        for chat_id in service.db.active_chat_ids():
            notification_date = notification_date_factory() if notification_date_factory else datetime.now(SGT).date()
            try:
                text = factory(chat_id)
                if not text:
                    continue
                message_id = telegram.send_message_sync(chat_id, text)
                service.db.record_notification_event(
                    kind,
                    notification_date,
                    chat_id=chat_id,
                    status="sent",
                    message_id=message_id,
                )
            except Exception as exc:
                logger.exception("Scheduled notification failed", extra={"chat_id": chat_id, "kind": kind})
                service.db.record_notification_event(
                    kind,
                    notification_date,
                    chat_id=chat_id,
                    status="failed",
                    error=str(exc),
                )

    scheduler.add_job(
        lambda: send_to_all_active_chats("morning-goal-reminder", lambda chat_id: service.morning_reminder(chat_id=chat_id)),
        CronTrigger(hour=8, minute=0, timezone=SGT),
        id="morning-goal-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats("missing-goals-reminder", lambda chat_id: service.missing_goals_reminder(chat_id=chat_id)),
        CronTrigger(hour=9, minute=30, timezone=SGT),
        id="missing-goals-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats(
            "goal-deadline-summary",
            lambda chat_id: service.goal_deadline_summary(datetime.now(SGT).date(), chat_id=chat_id),
        ),
        CronTrigger(hour=10, minute=0, timezone=SGT),
        id="goal-deadline-summary",
        replace_existing=True,
    )
    for hour in (20, 22):
        scheduler.add_job(
            lambda hour=hour: send_to_all_active_chats(
                f"completion-reminder-{hour}", lambda chat_id: service.completion_reminder(chat_id=chat_id)
            ),
            CronTrigger(hour=hour, minute=0, timezone=SGT),
            id=f"completion-reminder-{hour}",
            replace_existing=True,
        )
    scheduler.add_job(
        lambda: send_to_all_active_chats(
            "daily-close",
            lambda chat_id: service.close_day_summary(chat_id=chat_id, checkin_date=datetime.now(SGT).date() - timedelta(days=1)),
            notification_date_factory=lambda: datetime.now(SGT).date() - timedelta(days=1),
        ),
        CronTrigger(hour=5, minute=0, timezone=SGT),
        id="daily-close",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats("monthly-summary", lambda chat_id: service.month_score(chat_id=chat_id)),
        CronTrigger(day="last", hour=21, minute=0, timezone=SGT),
        id="monthly-summary",
        replace_existing=True,
    )
    return scheduler
