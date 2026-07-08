from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.db import Database
from app.domain import net_settlement
from app.parsing import parse_done_count, parse_goals

SGT = ZoneInfo("Asia/Singapore")


class AccountabilityService:
    def __init__(self, db: Database, *, penalty_amount: int = 5):
        self.db = db
        self.penalty_amount = penalty_amount

    def today(self) -> date:
        return datetime.now(SGT).date()

    def current_checkin_date(self) -> date:
        now = datetime.now(SGT)
        if now.hour < 5:
            return now.date() - timedelta(days=1)
        return now.date()

    def handle_text(self, user_id: int, username: str | None, display_name: str, chat_id: int, text: str) -> str | None:
        text = text.strip()
        self.db.register_chat(chat_id)

        if text.lower().startswith("/register"):
            self.db.register_user(user_id, username, display_name)
            users = self.db.active_users()
            roster = "\n".join(f"{idx}. {u['display_name']}" for idx, u in enumerate(users, start=1))
            return f"Registered {display_name} ✅\n\nCurrent players:\n{roster}"

        if text.lower().startswith("/rules"):
            return self.rules_text()

        if text.lower().startswith("/help"):
            return self.help_text()

        if not self.db.is_registered(user_id):
            return "Please /register first so I know you are part of the accountability challenge."

        goals = parse_goals(text)
        if goals is not None:
            checkin_date = self.today()
            late = datetime.now(SGT).time().hour >= 10
            self.db.upsert_goals(user_id, checkin_date, goals, late=late, chat_id=chat_id)
            late_note = "\nMarked late because this was after 10:00am." if late else ""
            return (
                f"Goals recorded for {display_name} ✅{late_note}\n\n"
                + "\n".join(f"{idx}. {goal}" for idx, goal in enumerate(goals, start=1))
            )

        if text.lower().startswith("/goals"):
            return "Please submit exactly 3 goals, one per line.\n\nExample:\n/goals\n- goal 1\n- goal 2\n- goal 3"

        if text.lower().startswith("/done"):
            count = parse_done_count(text)
            if count is None:
                return "Use `/done 0`, `/done 1`, `/done 2`, or `/done 3`."
            checkin_date = self.current_checkin_date()
            self.db.upsert_completion(user_id, checkin_date, count)
            result = "Pass ✅" if count >= 2 else "Fail ❌"
            return f"{display_name}: {count}/3 recorded for {checkin_date.isoformat()} — {result}"

        if text.lower().startswith("/today"):
            return self.today_summary(self.current_checkin_date())

        if text.lower().startswith("/score") or text.lower().startswith("/summary"):
            return self.month_score()

        return None

    def help_text(self) -> str:
        return (
            "## Accountability Bot Commands\n\n"
            "- `/register` — join the challenge\n"
            "- `/goals` + 3 bullet lines — submit today's goals\n"
            "- `/done 0..3` — report completed goals\n"
            "- `/today` — show today's status\n"
            "- `/score` — show current month settlement\n"
            "- `/rules` — show rules"
        )

    def rules_text(self) -> str:
        return (
            "## Rules\n\n"
            "1. Submit exactly 3 goals by 10:00am Singapore time.\n"
            "2. Complete at least 2/3 goals to pass.\n"
            "3. Report with `/done 0`, `/done 1`, `/done 2`, or `/done 3` by 5:00am next day.\n"
            "4. Missing goals or missing completion report = failed day.\n"
            f"5. Month end net settlement: more failed days pays ${self.penalty_amount} × difference."
        )

    def today_summary(self, checkin_date: date) -> str:
        rows = self.db.checkins_for_day(checkin_date)
        if not rows:
            return f"No check-ins recorded yet for {checkin_date.isoformat()}."
        lines = [f"## Daily Status — {checkin_date.isoformat()}", ""]
        for row in rows:
            completed = row.get("completed_count")
            completed_text = "not reported" if completed is None else f"{completed}/3"
            result = row.get("result") or "pending"
            emoji = "✅" if result == "pass" else "❌" if result == "fail" else "⏳"
            lines.append(f"- {row['display_name']}: {completed_text} — {emoji} {result}")
        return "\n".join(lines)

    def month_score(self) -> str:
        now = datetime.now(SGT)
        failures = self.db.failed_days_for_month(now.year, now.month)
        settlement = net_settlement(failures, self.penalty_amount)
        lines = [f"## Score — {now:%B %Y}", ""]
        for name, failed in failures.items():
            lines.append(f"- {name}: {failed} failed day(s)")
        lines.append("")
        if settlement["amount"] == 0:
            lines.append("Settlement: tied — nobody pays.")
        else:
            lines.append(f"Settlement: {settlement['payer']} pays {settlement['receiver']} ${settlement['amount']}.")
        return "\n".join(lines)

    def morning_reminder(self) -> str:
        return (
            "## Morning Check-in ☀️\n\n"
            "Submit your 3 goals before 10:00am Singapore time.\n\n"
            "Format:\n/goals\n- goal 1\n- goal 2\n- goal 3"
        )

    def missing_goals_reminder(self, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.db.missing_goal_users(day)
        if not missing:
            return "Everyone has submitted goals ✅"
        mentions = ", ".join(self._mention(u) for u in missing)
        return f"Goal reminder ⏰\n\nStill missing goals for {day.isoformat()}: {mentions}"

    def completion_reminder(self, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.db.missing_completion_users(day)
        if not missing:
            return "Everyone has reported completion ✅"
        mentions = ", ".join(self._mention(u) for u in missing)
        return f"Completion reminder 🌙\n\nStill missing `/done 0..3` for {day.isoformat()}: {mentions}"

    def close_day_summary(self, checkin_date: date | None = None) -> str:
        day = checkin_date or (self.today() - timedelta(days=1))
        self.db.close_day(day)
        return self.today_summary(day) + "\n\n" + self.month_score()

    def _mention(self, user: dict) -> str:
        if user.get("username"):
            return f"@{user['username']}"
        return user["display_name"]
