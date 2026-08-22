from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.repositories.checkins import CheckinRepository
from app.services.summaries import SummaryService

SGT = ZoneInfo("Asia/Singapore")
DIVIDER = "━━━━━━━━━━━━"


def h(value: object) -> str:
    return escape(str(value), quote=False)


def short_date(value: date) -> str:
    return value.strftime("%d %b %Y")


def command_example(text: str) -> str:
    return f"<pre>{h(text)}</pre>"


class ReminderService:
    def __init__(self, checkins: CheckinRepository, summaries: SummaryService):
        self.checkins = checkins
        self.summaries = summaries

    def today(self) -> date:
        return datetime.now(SGT).date()

    def morning_reminder(self, *, chat_id: int | None = None, checkin_date: date | None = None) -> str | None:
        reminder_blocks = ""
        if chat_id is not None:
            day = checkin_date or self.today()
            missing = self.checkins.missing_goal_users(day, chat_id=chat_id)
            if not missing:
                return None
            drafted_ids = {u["telegram_user_id"] for u in self.checkins.draft_goal_users(day, chat_id=chat_id)}
            drafted = [u for u in missing if u["telegram_user_id"] in drafted_ids]
            no_goals = [u for u in missing if u["telegram_user_id"] not in drafted_ids]
            blocks = []
            if drafted:
                blocks.append("<b>Draft ready — confirm or replace</b>\n" + ", ".join(self._mention(u) for u in drafted) + "\nUse <code>/confirmgoals</code>, or send fresh <code>/goals</code>.")
            if no_goals:
                blocks.append("<b>Still missing goals</b>\n" + ", ".join(self._mention(u) for u in no_goals))
            reminder_blocks = "\n\n" + "\n\n".join(blocks)
        return (
            "<b>☀️ Morning Check-in</b>\n"
            f"{DIVIDER}\n"
            "Submit your 3 goals before <b>10:00am SGT</b>."
            f"{reminder_blocks}\n\n"
            "<b>Copy this format</b>\n"
            + command_example("/goals\n- goal 1\n- goal 2\n- goal 3")
        )

    def missing_goals_reminder(self, *, chat_id: int, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.checkins.missing_goal_users(day, chat_id=chat_id)
        if not missing:
            return None
        drafted_ids = {u["telegram_user_id"] for u in self.checkins.draft_goal_users(day, chat_id=chat_id)}
        drafted = [u for u in missing if u["telegram_user_id"] in drafted_ids]
        no_goals = [u for u in missing if u["telegram_user_id"] not in drafted_ids]
        blocks = []
        if drafted:
            blocks.append(
                "<b>Draft ready — confirm or replace</b>\n"
                + ", ".join(self._mention(u) for u in drafted)
                + "\nSend <code>/confirmgoals</code>, or fresh <code>/goals</code> to replace the draft."
            )
        if no_goals:
            blocks.append(
                f"<b>Still missing goals for {short_date(day)}</b>\n"
                + ", ".join(self._mention(u) for u in no_goals)
                + "\nSend <code>/goals</code> with 3 bullet lines before 10:00am."
            )
        return "<b>⏰ Goal reminder</b>\n" f"{DIVIDER}\n" + "\n\n".join(blocks)

    def completion_reminder(self, *, chat_id: int, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.checkins.missing_completion_users(day, chat_id=chat_id)
        if not missing:
            return None
        mentions = ", ".join(self._mention(u) for u in missing)
        return (
            "<b>🌙 Completion reminder</b>\n"
            f"{DIVIDER}\n"
            f"Still missing <code>/done 0..3</code> for <b>{short_date(day)}</b>:\n{mentions}\n\n"
            "2/3 or 3/3 = pass. 0/3, 1/3, or no report = fail."
        )

    def close_day_summary(self, *, chat_id: int, checkin_date: date | None = None) -> str:
        day = checkin_date or (self.today() - timedelta(days=1))
        self.checkins.close_day(day, chat_id=chat_id)
        return self.summaries.today_summary(day, chat_id=chat_id) + "\n\n" + self.summaries.month_score(chat_id=chat_id)

    def _mention(self, user: dict) -> str:
        if user.get("username"):
            return f"@{h(user['username'])}"
        user_id = user.get("telegram_user_id")
        display_name = h(user["display_name"])
        if user_id is not None:
            return f'<a href="tg://user?id={int(user_id)}">{display_name}</a>'
        return display_name
