from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.db import Database
from app.domain import net_settlement
from app.parsing import parse_done_count, parse_goals
from app.qotd import QotdApiClient, QotdClient, QotdUnavailable

SGT = ZoneInfo("Asia/Singapore")
MAX_PLAYERS_PER_GROUP = 2


def h(value: object) -> str:
    return escape(str(value), quote=False)


class AccountabilityService:
    def __init__(self, db: Database, *, penalty_amount: int = 5, qotd_client: QotdClient | None = None):
        self.db = db
        self.penalty_amount = penalty_amount
        self.qotd_client = qotd_client or QotdApiClient()

    def today(self) -> date:
        return datetime.now(SGT).date()

    def current_checkin_date(self) -> date:
        now = datetime.now(SGT)
        if now.hour < 5:
            return now.date() - timedelta(days=1)
        return now.date()

    def handle_text(
        self,
        user_id: int,
        username: str | None,
        display_name: str,
        chat_id: int,
        text: str,
        *,
        chat_type: str | None = None,
    ) -> str | None:
        text = text.strip()
        if chat_type == "private":
            return self.private_chat_text()

        self.db.register_chat(chat_id)

        if text.lower().startswith("/register"):
            users = self.db.active_users(chat_id=chat_id)
            already_registered = any(int(u["telegram_user_id"]) == int(user_id) for u in users)
            if not already_registered and len(users) >= MAX_PLAYERS_PER_GROUP:
                return (
                    "This group already has 2 players registered ✅\n\n"
                    "This bot is designed for a 2-person accountability group. "
                    "If you need to swap a player, ask a group admin to remove the old registration first."
                )
            self.db.register_user(user_id, username, display_name, chat_id=chat_id)
            users = self.db.active_users(chat_id=chat_id)
            roster = "\n".join(f"{idx}. {h(u['display_name'])}" for idx, u in enumerate(users, start=1))
            return f"Registered {h(display_name)} ✅\n\n<b>Current players</b>\n{roster}"

        if text.lower().startswith("/rules"):
            return self.rules_text()

        if text.lower().startswith("/help"):
            return self.help_text()

        if not self.db.is_registered(user_id, chat_id=chat_id):
            return "Please register first with <code>/register</code> so I know you are part of the accountability challenge."

        goals = parse_goals(text)
        if goals is not None:
            checkin_date = self.today()
            late = datetime.now(SGT).time().hour >= 10
            self.db.upsert_goals(user_id, checkin_date, goals, late=late, chat_id=chat_id)
            late_note = "\nMarked late because this was after 10:00am." if late else ""
            return (
                f"Goals recorded for {h(display_name)} ✅{late_note}\n\n"
                + "\n".join(f"{idx}. {h(goal)}" for idx, goal in enumerate(goals, start=1))
            )

        if text.lower().startswith("/goals"):
            return "Please submit exactly 3 goals, one per line.\n\nExample:\n<code>/goals\n- goal 1\n- goal 2\n- goal 3</code>"

        if text.lower().startswith("/done"):
            count = parse_done_count(text)
            if count is None:
                return "Use <code>/done 0</code>, <code>/done 1</code>, <code>/done 2</code>, or <code>/done 3</code>."
            checkin_date = self.current_checkin_date()
            self.db.upsert_completion(user_id, checkin_date, count, chat_id=chat_id)
            result = "Pass ✅" if count >= 2 else "Fail ❌"
            return f"{h(display_name)}: {count}/3 recorded for {checkin_date.isoformat()} — {result}"

        if text.lower().startswith("/today"):
            return self.today_summary(self.current_checkin_date(), chat_id=chat_id)

        if text.lower().startswith("/score") or text.lower().startswith("/summary"):
            return self.month_score(chat_id=chat_id)

        return None

    def intro_text(self) -> str:
        return (
            "<b>Welcome to the Accountability Bot 👋</b>\n\n"
            "I help a 2-person Telegram group run a simple daily 3-goal accountability challenge.\n\n"
            "<b>How to start</b>\n"
            "1. Each person sends <code>/register</code> once.\n"
            "2. Every morning, submit exactly 3 goals with <code>/goals</code>.\n"
            "3. At night, report completion with <code>/done 0</code>, <code>/done 1</code>, <code>/done 2</code>, or <code>/done 3</code>.\n\n"
            "Passing means completing 2/3 or 3/3 goals. Missing goals or missing completion counts as a failed day.\n\n"
            "Tap the bot command menu, or send <code>/help</code> anytime."
        )

    def private_chat_text(self) -> str:
        return (
            "<b>Hey 👋 I can't run in a private chat.</b>\n\n"
            "I'm designed for a Telegram group with exactly 2 people, so both players can see the daily goals, "
            "reminders, results, and month-end settlement.\n\n"
            "Please add <b>@be_accountable_bot</b> to a group with 2 people, then each person can send "
            "<code>/register</code> there to start."
        )

    def help_text(self) -> str:
        return (
            "<b>Accountability Bot Commands</b>\n\n"
            "<code>/register</code> — join the challenge\n"
            "<code>/goals</code> + 3 bullet lines — submit today's goals\n"
            "<code>/done 0</code> to <code>/done 3</code> — report completed goals\n"
            "<code>/today</code> — show today's status\n"
            "<code>/score</code> — show current month settlement\n"
            "<code>/rules</code> — show rules\n\n"
            "Example:\n"
            "<code>/goals\n- investment stuff\n- intervals\n- read</code>"
        )

    def rules_text(self) -> str:
        return (
            "<b>Rules</b>\n\n"
            "1. Submit exactly 3 goals by 10:00am Singapore time.\n"
            "2. Complete at least 2/3 goals to pass.\n"
            "3. Report with <code>/done 0</code>, <code>/done 1</code>, <code>/done 2</code>, or <code>/done 3</code> by 5:00am next day.\n"
            "4. Missing goals or missing completion report = failed day.\n"
            f"5. Month end net settlement: more failed days pays ${self.penalty_amount} × difference."
        )

    def today_summary(self, checkin_date: date, *, chat_id: int, now: datetime | None = None) -> str:
        rows = self.db.checkins_for_day(checkin_date, chat_id=chat_id)
        if not rows:
            return f"No registered players found for {checkin_date.isoformat()}."
        now = now or datetime.now(SGT)
        lines = [f"<b>Daily Status — {checkin_date.isoformat()}</b>"]
        for row in rows:
            completed = row.get("completed_count")
            goals = row.get("goals") or []
            completed_text = "not reported" if completed is None else f"{completed}/3"
            if not goals:
                completed_text = "no goals logged"
            result = self._display_result(row, checkin_date, now=now)
            emoji = "✅" if result == "pass" else "❌" if result == "fail" else "⏳"
            lines.append("")
            lines.append(f"<b>{h(row['display_name'])}</b>")
            lines.append(f"Status: {emoji} {h(result)} — {h(completed_text)}")
            if goals:
                lines.append("Goals")
                for idx, goal in enumerate(goals, start=1):
                    lines.append(f"{idx}. {h(goal)}")
        return "\n".join(lines)

    def goal_confirmation_summary(self, checkin_date: date, *, chat_id: int) -> str:
        return (
            "<b>Great thanks for keying your goals</b>\n\n"
            + self.goals_block(checkin_date, chat_id=chat_id)
            + "\n\n"
            + self.qotd()
        )

    def goals_block(self, checkin_date: date, *, chat_id: int) -> str:
        rows = self.db.checkins_for_day(checkin_date, chat_id=chat_id)
        lines = [f"<b>Today's Goals — {checkin_date.isoformat()}</b>"]
        for row in rows:
            goals = row.get("goals") or []
            if not goals:
                continue
            lines.append("")
            lines.append(f"<b>{h(row['display_name'])}</b>")
            for idx, goal in enumerate(goals, start=1):
                lines.append(f"{idx}. {h(goal)}")
        return "\n".join(lines)

    def qotd(self) -> str:
        try:
            quote, author = self.qotd_client.quote_of_the_day()
        except QotdUnavailable:
            return "<b>QOTD</b>\n<i>Quote temporarily unavailable.</i>"

        lines = ["<b>QOTD</b>", f"<i>{h(quote)}</i>"]
        if author:
            lines.append(f"— {h(author)}")
        return "\n".join(lines)

    def _display_result(self, row: dict, checkin_date: date, *, now: datetime) -> str:
        goals = row.get("goals") or []
        completed = row.get("completed_count")
        goal_deadline = datetime.combine(checkin_date, time(10, 0), tzinfo=SGT)
        completion_deadline = datetime.combine(checkin_date + timedelta(days=1), time(5, 0), tzinfo=SGT)

        if not goals:
            return "fail" if now >= goal_deadline else "pending"
        if row.get("goals_status") == "late_submitted":
            return "fail"
        if completed is None:
            return "fail" if now >= completion_deadline else "pending"
        return "pass" if int(completed) >= 2 else "fail"

    def month_score(self, *, chat_id: int, year: int | None = None, month: int | None = None) -> str:
        now = datetime.now(SGT)
        score_year = year or now.year
        score_month = month or now.month
        failures = self.db.failed_days_for_month(score_year, score_month, chat_id=chat_id)
        settlement = net_settlement(failures, self.penalty_amount)
        month_name = date(score_year, score_month, 1).strftime("%B %Y")
        lines = [f"<b>Score — {month_name}</b>", ""]
        for name, failed in failures.items():
            lines.append(f"- {h(name)}: {failed} failed day(s)")
        lines.append("")
        if settlement["amount"] == 0:
            lines.append("Settlement: tied — nobody pays.")
        else:
            lines.append(f"Settlement: {h(settlement['payer'])} pays {h(settlement['receiver'])} ${settlement['amount']}.")
        return "\n".join(lines)

    def morning_reminder(self) -> str:
        return (
            "<b>Morning Check-in ☀️</b>\n\n"
            "Submit your 3 goals before 10:00am Singapore time.\n\n"
            "Format:\n<code>/goals\n- goal 1\n- goal 2\n- goal 3</code>"
        )

    def missing_goals_reminder(self, *, chat_id: int, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.db.missing_goal_users(day, chat_id=chat_id)
        if not missing:
            return None
        mentions = ", ".join(self._mention(u) for u in missing)
        return f"<b>Goal reminder ⏰</b>\n\nStill missing goals for {day.isoformat()}: {mentions}"

    def completion_reminder(self, *, chat_id: int, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.db.missing_completion_users(day, chat_id=chat_id)
        if not missing:
            return None
        mentions = ", ".join(self._mention(u) for u in missing)
        return f"<b>Completion reminder 🌙</b>\n\nStill missing <code>/done 0..3</code> for {day.isoformat()}: {mentions}"

    def close_day_summary(self, *, chat_id: int, checkin_date: date | None = None) -> str:
        day = checkin_date or (self.today() - timedelta(days=1))
        self.db.close_day(day, chat_id=chat_id)
        return self.today_summary(day, chat_id=chat_id) + "\n\n" + self.month_score(chat_id=chat_id)

    def _mention(self, user: dict) -> str:
        if user.get("username"):
            return f"@{h(user['username'])}"
        user_id = user.get("telegram_user_id")
        display_name = h(user["display_name"])
        if user_id is not None:
            return f'<a href="tg://user?id={int(user_id)}">{display_name}</a>'
        return display_name
