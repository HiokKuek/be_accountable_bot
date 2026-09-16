from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.handlers.telegram.response_mapper import TelegramClient, TelegramResponseMapper
from app.repositories.notifications import NotificationRepository
from app.repositories.participants import ParticipantRepository
from app.services.reminders import ReminderService
from app.services.summaries import SummaryService

SGT = ZoneInfo("Asia/Singapore")
logger = logging.getLogger(__name__)


def build_scheduler(
    reminders: ReminderService,
    summaries: SummaryService,
    telegram: TelegramClient,
    participants: ParticipantRepository,
    notifications: NotificationRepository,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=SGT)
    mapper = TelegramResponseMapper(telegram)

    def send_to_all_active_chats(kind, factory, notification_date_factory=None) -> None:
        for chat_id in participants.active_chat_ids():
            notification_date = notification_date_factory() if notification_date_factory else datetime.now(SGT).date()
            try:
                text = factory(chat_id)
                if not text:
                    continue
                message_id = mapper.send_reply_sync(chat_id, text)
                notifications.record_notification_event(
                    kind,
                    notification_date,
                    chat_id=chat_id,
                    status="sent",
                    message_id=message_id,
                )
            except Exception as exc:
                logger.exception("Scheduled notification failed", extra={"chat_id": chat_id, "kind": kind})
                notifications.record_notification_event(
                    kind,
                    notification_date,
                    chat_id=chat_id,
                    status="failed",
                    error=str(exc),
                )

    def pin_goal_summary_for_all_active_chats() -> None:
        notification_date = datetime.now(SGT).date()
        for chat_id in participants.active_chat_ids():
            message_id = notifications.goal_summary_message_id(notification_date, chat_id=chat_id)
            if message_id is None:
                continue
            prior_events = notifications.notification_events_for_day(notification_date, chat_id=chat_id)
            if any(event["kind"] == "goal-summary-pin" and event["status"] == "sent" for event in prior_events):
                continue
            try:
                pinned = telegram.pin_chat_message_sync(chat_id, message_id)
                if not pinned:
                    raise RuntimeError("pinChatMessage returned false")
                notifications.record_notification_event(
                    "goal-summary-pin",
                    notification_date,
                    chat_id=chat_id,
                    status="sent",
                    message_id=message_id,
                )
            except Exception as exc:
                logger.exception("Scheduled goal summary pin failed", extra={"chat_id": chat_id, "kind": "goal-summary-pin"})
                notifications.record_notification_event(
                    "goal-summary-pin",
                    notification_date,
                    chat_id=chat_id,
                    status="failed",
                    message_id=message_id,
                    error=str(exc),
                )

    scheduler.add_job(
        lambda: send_to_all_active_chats("morning-goal-reminder", lambda chat_id: reminders.morning_reminder(chat_id=chat_id)),
        CronTrigger(hour=8, minute=0, timezone=SGT),
        id="morning-goal-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats("missing-goals-reminder", lambda chat_id: reminders.missing_goals_reminder(chat_id=chat_id)),
        CronTrigger(hour=9, minute=30, timezone=SGT),
        id="missing-goals-reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats(
            "goal-deadline-summary",
            lambda chat_id: summaries.goal_deadline_summary(datetime.now(SGT).date(), chat_id=chat_id),
        ),
        CronTrigger(hour=10, minute=0, timezone=SGT),
        id="goal-deadline-summary",
        replace_existing=True,
    )
    scheduler.add_job(
        pin_goal_summary_for_all_active_chats,
        CronTrigger(hour=22, minute=0, timezone=SGT),
        id="goal-summary-pin",
        replace_existing=True,
    )
    for hour in (20, 22):
        scheduler.add_job(
            lambda hour=hour: send_to_all_active_chats(
                f"completion-reminder-{hour}",
                lambda chat_id: reminders.completion_reminder(chat_id=chat_id),
            ),
            CronTrigger(hour=hour, minute=0, timezone=SGT),
            id=f"completion-reminder-{hour}",
            replace_existing=True,
        )
    scheduler.add_job(
        lambda: send_to_all_active_chats(
            "daily-close",
            lambda chat_id: reminders.close_day_summary(chat_id=chat_id, checkin_date=datetime.now(SGT).date() - timedelta(days=1)),
            notification_date_factory=lambda: datetime.now(SGT).date() - timedelta(days=1),
        ),
        CronTrigger(hour=5, minute=0, timezone=SGT),
        id="daily-close",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: send_to_all_active_chats("monthly-summary", lambda chat_id: summaries.month_score(chat_id=chat_id)),
        CronTrigger(day="last", hour=21, minute=0, timezone=SGT),
        id="monthly-summary",
        replace_existing=True,
    )
    return scheduler
