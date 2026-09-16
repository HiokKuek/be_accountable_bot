from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.domain.rules import monthly_leaderboard
from app.repositories.checkins import CheckinRepository
from app.services.content import ContentService

SGT = ZoneInfo("Asia/Singapore")
DIVIDER = "━━━━━━━━━━━━"


def h(value: object) -> str:
    return escape(str(value), quote=False)


def short_date(value: date) -> str:
    return value.strftime("%d %b %Y")


def goal_lines(goals: list[str]) -> list[str]:
    return [f"{idx}. {h(goal)}" for idx, goal in enumerate(goals, start=1)]


class SummaryService:
    def __init__(self, checkins: CheckinRepository, content: ContentService, *, penalty_amount: int = 5):
        self.checkins = checkins
        self.content = content
        self.penalty_amount = penalty_amount

    def today_summary(self, checkin_date: date, *, chat_id: int, now: datetime | None = None) -> str:
        rows = self.checkins.checkins_for_day(checkin_date, chat_id=chat_id)
        if not rows:
            return f"<b>📅 Daily Status — {short_date(checkin_date)}</b>\n{DIVIDER}\nNo registered players found."
        now = now or datetime.now(SGT)
        lines = [f"<b>📅 Daily Status — {short_date(checkin_date)}</b>", DIVIDER]
        for row in rows:
            completed = row.get("completed_count")
            goals = row.get("goals") or []
            completed_text = "not reported" if completed is None else f"{completed}/3"
            if not goals:
                completed_text = "no goals logged"
            result = self._display_result(row, checkin_date, now=now)
            emoji, label = self._status_badge(result)
            lines.append("")
            lines.append(f"<b>👤 {h(row['display_name'])}</b>")
            lines.append(f"Status: <b>{emoji} {label}</b>")
            lines.append(f"Progress: <code>{h(completed_text)}</code>")
            if goals:
                lines.append("<b>Goals</b>")
                lines.extend(goal_lines(goals))
        return "\n".join(lines)

    def goal_confirmation_summary(self, checkin_date: date, *, chat_id: int) -> str:
        return (
            "<b>🎯 All goals are keyed</b>\n"
            "Nice — today's game board is set.\n\n"
            + self.goals_block(checkin_date, chat_id=chat_id)
            + "\n\n"
            + self.content.qotd()
        )

    def goal_deadline_summary(self, checkin_date: date, *, chat_id: int) -> str | None:
        rows = self.checkins.checkins_for_day(checkin_date, chat_id=chat_id)
        if not rows:
            return None
        missing = self.checkins.missing_goal_users(checkin_date, chat_id=chat_id)
        if not missing:
            return None
        submitted_count = len(rows) - len(missing)
        total_count = len(rows)
        mentions = ", ".join(self._mention(u) for u in missing)
        missing_block = f"\n\n<b>Still missing</b>\n{mentions}" if mentions else ""
        return (
            "<b>⏰ Goal deadline reached</b>\n"
            f"Submitted: <b>{submitted_count}/{total_count}</b>\n"
            f"{DIVIDER}\n"
            + self.goals_block(checkin_date, chat_id=chat_id)
            + missing_block
            + "\n\n"
            + self.content.qotd()
        )

    def goals_block(self, checkin_date: date, *, chat_id: int) -> str:
        rows = self.checkins.checkins_for_day(checkin_date, chat_id=chat_id)
        lines = [f"<b>📝 Today's Goals — {short_date(checkin_date)}</b>", DIVIDER]
        for row in rows:
            goals = row.get("goals") or []
            if not goals:
                continue
            lines.append("")
            lines.append(f"<b>👤 {h(row['display_name'])}</b>")
            lines.extend(goal_lines(goals))
        return "\n".join(lines)

    def month_score(self, *, chat_id: int, year: int | None = None, month: int | None = None) -> str:
        now = datetime.now(SGT)
        score_year = year or now.year
        score_month = month or now.month
        failures = self.checkins.failed_days_for_month(score_year, score_month, chat_id=chat_id)
        leaderboard = monthly_leaderboard(failures, self.penalty_amount)
        month_name = date(score_year, score_month, 1).strftime("%B %Y")
        lines = [f"<b>🏆 Leaderboard — {month_name}</b>", DIVIDER]
        if not leaderboard:
            lines.append("No registered participants found.")
            return "\n".join(lines)

        total_penalty = 0
        for entry in leaderboard:
            failed = int(entry["failed_days"])
            penalty = int(entry["penalty"])
            total_penalty += penalty
            day_word = "day" if failed == 1 else "days"
            lines.append(f"{entry['rank']}. {h(entry['name'])} — <b>{failed}</b> failed {day_word} — <b>${penalty}</b>")
        lines.append("")
        lines.append(f"Group total: <b>${total_penalty}</b>")
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

    @staticmethod
    def _status_badge(result: str) -> tuple[str, str]:
        if result == "pass":
            return "✅", "Pass"
        if result == "fail":
            return "❌", "Fail"
        return "⏳", "Pending"

    def _mention(self, user: dict) -> str:
        if user.get("username"):
            return f"@{h(user['username'])}"
        user_id = user.get("telegram_user_id")
        display_name = h(user["display_name"])
        if user_id is not None:
            return f'<a href="tg://user?id={int(user_id)}">{display_name}</a>'
        return display_name
