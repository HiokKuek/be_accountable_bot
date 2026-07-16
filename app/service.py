from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.db import Database
from app.domain import monthly_leaderboard
from app.parsing import parse_done_count, parse_goals
from app.qotd import QotdApiClient, QotdClient, QotdUnavailable

SGT = ZoneInfo("Asia/Singapore")
DIVIDER = "━━━━━━━━━━━━"


def h(value: object) -> str:
    return escape(str(value), quote=False)


def short_date(value: date) -> str:
    return value.strftime("%d %b %Y")


def command_example(text: str) -> str:
    return f"<pre>{h(text)}</pre>"


def goal_lines(goals: list[str]) -> list[str]:
    return [f"{idx}. {h(goal)}" for idx, goal in enumerate(goals, start=1)]


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

    def goal_submission_is_next_day_draft(
        self, user_id: int, *, chat_id: int, now: datetime | None = None
    ) -> bool:
        now = now or datetime.now(SGT)
        completion_date = now.date() - timedelta(days=1) if now.hour < 5 else now.date()
        draft_date = completion_date + timedelta(days=1)
        completion = self.db.get_checkin(user_id, completion_date, chat_id=chat_id)
        return now.date() < draft_date and bool(completion and completion.get("completed_count") == 3)

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
            self.db.register_user(user_id, username, display_name, chat_id=chat_id)
            users = self.db.active_users(chat_id=chat_id)
            roster = "\n".join(f"{idx}. {h(u['display_name'])}" for idx, u in enumerate(users, start=1))
            return (
                f"<b>✅ Registered {h(display_name)}</b>\n"
                f"{DIVIDER}\n"
                f"Participants: {len(users)}\n\n"
                "<b>Current participants</b>\n"
                f"{roster}\n\n"
                "<b>Next</b>\n"
                "Anyone else who wants to join can send <code>/register</code>. "
                "Submit your own 3 goals with <code>/goals</code>."
            )

        if text.lower().startswith("/rules"):
            return self.rules_text()

        if text.lower().startswith("/help"):
            return self.help_text()

        if not self.db.is_registered(user_id, chat_id=chat_id):
            return (
                "<b>👋 Register first</b>\n"
                f"{DIVIDER}\n"
                "Send <code>/register</code> in this group so I know you are part of the accountability challenge."
            )

        if text.lower().startswith("/remove"):
            parts = text.split(maxsplit=1)
            if len(parts) == 1:
                return (
                    "<b>🛠️ Remove a participant</b>\n"
                    f"{DIVIDER}\n"
                    "Use <code>/remove @username</code> or <code>/remove Display Name</code>."
                )
            removed = self.db.deactivate_participant_by_name(chat_id, parts[1])
            if removed is None:
                return (
                    "<b>⚠️ Participant not found</b>\n"
                    f"{DIVIDER}\n"
                    f"I couldn't find an active participant matching <code>{h(parts[1])}</code> in this group."
                )
            return (
                f"<b>✅ Removed {h(removed['display_name'])}</b>\n"
                f"{DIVIDER}\n"
                "They will no longer be tagged in reminders or included in future scoreboards for this group."
            )

        goals = parse_goals(text)
        if goals is not None:
            now = datetime.now(SGT)
            checkin_date = now.date()
            completion_date = self.current_checkin_date()
            draft_date = completion_date + timedelta(days=1)
            if self.goal_submission_is_next_day_draft(user_id, chat_id=chat_id, now=now):
                self.db.upsert_goal_draft(user_id, draft_date, goals, chat_id=chat_id)
                return (
                    f"<b>📝 Goals drafted — {h(display_name)}</b>\n"
                    f"<i>For {short_date(draft_date)}</i>\n"
                    f"{DIVIDER}\n"
                    + "\n".join(goal_lines(goals))
                    + "\n\nSend <code>/goals</code> again tonight to overwrite this draft. "
                    "Tomorrow, send <code>/confirmgoals</code> to make it official, or send fresh <code>/goals</code> to replace it."
                )
            late = datetime.now(SGT).time().hour >= 10 and not self.db.has_registration_grace(
                user_id, checkin_date, chat_id=chat_id
            )
            self.db.upsert_goals(user_id, checkin_date, goals, late=late, chat_id=chat_id)
            late_note = "\n\n⚠️ <b>Late:</b> marked late because this was after 10:00am." if late else ""
            return (
                f"<b>✅ Goals recorded — {h(display_name)}</b>\n"
                f"<i>{short_date(checkin_date)}</i>{late_note}\n"
                f"{DIVIDER}\n"
                + "\n".join(goal_lines(goals))
            )

        if text.lower().startswith("/goals"):
            return (
                "<b>📝 Submit exactly 3 goals</b>\n"
                f"{DIVIDER}\n"
                "Send one goal per line. Copy this format:\n"
                + command_example("/goals\n- goal 1\n- goal 2\n- goal 3")
            )

        if text.lower().startswith("/confirmgoals"):
            checkin_date = self.today()
            late = datetime.now(SGT).time().hour >= 10 and not self.db.has_registration_grace(
                user_id, checkin_date, chat_id=chat_id
            )
            goals = self.db.promote_goal_draft(user_id, checkin_date, late=late, chat_id=chat_id)
            if goals is None:
                return (
                    "<b>📝 No draft to confirm</b>\n"
                    f"{DIVIDER}\n"
                    "Send <code>/goals</code> with 3 bullet lines to record today's goals."
                )
            late_note = "\n\n⚠️ <b>Late:</b> marked late because this was after 10:00am." if late else ""
            return (
                f"<b>✅ Draft confirmed — {h(display_name)}</b>\n"
                f"<i>{short_date(checkin_date)}</i>{late_note}\n"
                f"{DIVIDER}\n"
                + "\n".join(goal_lines(goals))
            )

        if text.lower().startswith("/done"):
            count = parse_done_count(text)
            if count is None:
                return (
                    "<b>🌙 Report completed goals</b>\n"
                    f"{DIVIDER}\n"
                    "Use one of these commands: <code>/done 0</code>, <code>/done 1</code>, "
                    "<code>/done 2</code>, or <code>/done 3</code>."
                )
            checkin_date = self.current_checkin_date()
            self.db.upsert_completion(user_id, checkin_date, count, chat_id=chat_id)
            passed = count >= 2
            result = "✅ Pass" if passed else "❌ Fail"
            encouragement = "Nice — 2/3 or better keeps the day green." if passed else "Reset tomorrow — log goals early and aim for 2/3."
            draft_prompt = (
                "\n\n<b>Plan ahead</b>\nSend <code>/goals</code> now to draft tomorrow's 3 goals."
                if count == 3
                else ""
            )
            return (
                f"<b>{result} recorded — {h(display_name)}</b>\n"
                f"{DIVIDER}\n"
                f"Date: <b>{short_date(checkin_date)}</b>\n"
                f"Progress: <b>{count}/3</b>\n\n"
                f"<i>{encouragement}</i>{draft_prompt}"
            )

        if text.lower().startswith("/today"):
            return self.today_summary(self.current_checkin_date(), chat_id=chat_id)

        if text.lower().startswith("/score") or text.lower().startswith("/summary"):
            return self.month_score(chat_id=chat_id)

        return None

    def intro_text(self) -> str:
        return (
            "<b>🎯 Accountability Bot</b>\n"
            "<i>Daily 3-goal challenge for Telegram groups.</i>\n"
            f"{DIVIDER}\n\n"
            "<b>Quick start</b>\n"
            "1. Each participant sends <code>/register</code> once.\n"
            "2. Every morning, submit exactly 3 goals with <code>/goals</code>.\n"
            "3. At night, report completion with <code>/done 0</code> to <code>/done 3</code>.\n\n"
            "<b>Pass / fail</b>\n"
            "✅ Pass: complete 2/3 or 3/3 goals.\n"
            "❌ Fail: missing goals, missing completion, 0/3, or 1/3.\n\n"
            "Tap the bot command menu, or send <code>/help</code> anytime."
        )

    def private_chat_text(self) -> str:
        return (
            "<b>👋 I can't run in a private chat</b>\n"
            f"{DIVIDER}\n"
            "I'm designed for a Telegram group so participants can see the daily goals, reminders, "
            "results, and leaderboard together.\n\n"
            "Add <b>@be_accountable_bot</b> to a group, then each participant sends "
            "<code>/register</code> there to start."
        )

    def help_text(self) -> str:
        return (
            "<b>🤖 Accountability Bot Commands</b>\n"
            f"{DIVIDER}\n"
            "<code>/register</code> — join the challenge\n"
            "<code>/goals</code> — submit today's 3 goals\n"
            "<code>/confirmgoals</code> — confirm a draft for today\n"
            "<code>/done 0</code> to <code>/done 3</code> — report completed goals\n"
            "<code>/today</code> — show today's status\n"
            "<code>/score</code> — show current month leaderboard\n"
            "<code>/remove @user</code> — remove an inactive participant\n"
            "<code>/rules</code> — show the rules\n\n"
            "<b>Goal format</b>\n"
            + command_example("/goals\n- investment review\n- intervals\n- read 10 pages")
        )

    def rules_text(self) -> str:
        return (
            "<b>📜 Rules</b>\n"
            f"{DIVIDER}\n"
            "1. Submit exactly 3 goals by <b>10:00am SGT</b>.\n"
            "2. Complete at least <b>2/3</b> goals to pass.\n"
            "3. Report with <code>/done 0</code> to <code>/done 3</code> by <b>5:00am next day</b>.\n"
            "4. Missing goals or missing completion report = failed day.\n"
            "5. After <code>/done 3</code>, you can send <code>/goals</code> that night to draft tomorrow's goals. Confirm them tomorrow with <code>/confirmgoals</code>, or replace them with fresh <code>/goals</code>.\n"
            "6. New participants who register after <b>10:00am SGT</b> start from tomorrow; same-day goals are optional and not marked late.\n"
            f"7. <code>/score</code> ranks the group by fewest failed days. Each failed day counts as <b>${self.penalty_amount}</b> in penalties."
        )

    def today_summary(self, checkin_date: date, *, chat_id: int, now: datetime | None = None) -> str:
        rows = self.db.checkins_for_day(checkin_date, chat_id=chat_id)
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
            + self.qotd()
        )

    def goal_deadline_summary(self, checkin_date: date, *, chat_id: int) -> str | None:
        rows = self.db.checkins_for_day(checkin_date, chat_id=chat_id)
        if not rows:
            return None
        missing = self.db.missing_goal_users(checkin_date, chat_id=chat_id)
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
            + self.qotd()
        )

    def goals_block(self, checkin_date: date, *, chat_id: int) -> str:
        rows = self.db.checkins_for_day(checkin_date, chat_id=chat_id)
        lines = [f"<b>📝 Today's Goals — {short_date(checkin_date)}</b>", DIVIDER]
        for row in rows:
            goals = row.get("goals") or []
            if not goals:
                continue
            lines.append("")
            lines.append(f"<b>👤 {h(row['display_name'])}</b>")
            lines.extend(goal_lines(goals))
        return "\n".join(lines)

    def qotd(self) -> str:
        try:
            quote, author = self.qotd_client.quote_of_the_day()
        except QotdUnavailable:
            return "<b>💬 QOTD</b>\n<blockquote><i>Quote temporarily unavailable.</i></blockquote>"

        lines = ["<b>💬 QOTD</b>", f"<blockquote><i>{h(quote)}</i></blockquote>"]
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

    def _status_badge(self, result: str) -> tuple[str, str]:
        if result == "pass":
            return "✅", "Pass"
        if result == "fail":
            return "❌", "Fail"
        return "⏳", "Pending"

    def month_score(self, *, chat_id: int, year: int | None = None, month: int | None = None) -> str:
        now = datetime.now(SGT)
        score_year = year or now.year
        score_month = month or now.month
        failures = self.db.failed_days_for_month(score_year, score_month, chat_id=chat_id)
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

    def morning_reminder(self, *, chat_id: int | None = None, checkin_date: date | None = None) -> str | None:
        reminder_blocks = ""
        if chat_id is not None:
            day = checkin_date or self.today()
            missing = self.db.missing_goal_users(day, chat_id=chat_id)
            if not missing:
                return None
            drafted_ids = {u["telegram_user_id"] for u in self.db.draft_goal_users(day, chat_id=chat_id)}
            drafted = [u for u in missing if u["telegram_user_id"] in drafted_ids]
            no_goals = [u for u in missing if u["telegram_user_id"] not in drafted_ids]
            blocks = []
            if drafted:
                blocks.append(
                    "<b>Draft ready — confirm or replace</b>\n"
                    + ", ".join(self._mention(u) for u in drafted)
                    + "\nUse <code>/confirmgoals</code>, or send fresh <code>/goals</code>."
                )
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
        missing = self.db.missing_goal_users(day, chat_id=chat_id)
        if not missing:
            return None
        drafted_ids = {u["telegram_user_id"] for u in self.db.draft_goal_users(day, chat_id=chat_id)}
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
        return (
            "<b>⏰ Goal reminder</b>\n"
            f"{DIVIDER}\n"
            + "\n\n".join(blocks)
        )

    def completion_reminder(self, *, chat_id: int, checkin_date: date | None = None) -> str | None:
        day = checkin_date or self.today()
        missing = self.db.missing_completion_users(day, chat_id=chat_id)
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
