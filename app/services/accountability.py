from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.domain.models import MessageContext, ReportDoneInput, SubmitGoalsInput
from app.repositories.checkins import CheckinRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.participants import ParticipantRepository
from app.services.content import AnimationReply, ContentService

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
    def __init__(
        self,
        participants: ParticipantRepository,
        checkins: CheckinRepository,
        notifications: NotificationRepository,
        *,
        penalty_amount: int = 5,
        content: ContentService | None = None,
    ):
        self.participants = participants
        self.checkins = checkins
        self.notifications = notifications
        self.penalty_amount = penalty_amount
        self.content = content or ContentService()

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
        completion = self.checkins.get_checkin(user_id, completion_date, chat_id=chat_id)
        return now.date() < draft_date and bool(completion and completion.get("completed_count") == 3)

    def register_participant(self, context: MessageContext) -> str:
        self.participants.register_user(context.user_id, context.username, context.display_name, chat_id=context.chat_id)
        users = self.participants.active_users(chat_id=context.chat_id)
        roster = "\n".join(f"{idx}. {h(u['display_name'])}" for idx, u in enumerate(users, start=1))
        return (
            f"<b>✅ Registered {h(context.display_name)}</b>\n"
            f"{DIVIDER}\n"
            f"Participants: {len(users)}\n\n"
            "<b>Current participants</b>\n"
            f"{roster}\n\n"
            "<b>Next</b>\n"
            "Anyone else who wants to join can send <code>/register</code>. "
            "Submit your own 3 goals with <code>/goals</code>."
        )

    def registration_required(self) -> str:
        return (
            "<b>👋 Register first</b>\n"
            f"{DIVIDER}\n"
            "Send <code>/register</code> in this group so I know you are part of the accountability challenge."
        )

    def remove_participant(self, context: MessageContext, name: str | None) -> str:
        if not name:
            return (
                "<b>🛠️ Remove a participant</b>\n"
                f"{DIVIDER}\n"
                "Use <code>/remove @username</code> or <code>/remove Display Name</code>."
            )
        removed = self.participants.deactivate_participant_by_name(context.chat_id, name)
        if removed is None:
            return (
                "<b>⚠️ Participant not found</b>\n"
                f"{DIVIDER}\n"
                f"I couldn't find an active participant matching <code>{h(name)}</code> in this group."
            )
        return (
            f"<b>✅ Removed {h(removed['display_name'])}</b>\n"
            f"{DIVIDER}\n"
            "They will no longer be tagged in reminders or included in future scoreboards for this group."
        )

    def goals_usage_text(self) -> str:
        return (
            "<b>📝 Submit exactly 3 goals</b>\n"
            f"{DIVIDER}\n"
            "Send one goal per line. Copy this format:\n"
            + command_example("/goals\n- goal 1\n- goal 2\n- goal 3")
        )

    def submit_goals(self, command: SubmitGoalsInput) -> str:
        context = command.context
        goals = command.goals
        now = datetime.now(SGT)
        checkin_date = now.date()
        completion_date = self.current_checkin_date()
        draft_date = completion_date + timedelta(days=1)
        if self.goal_submission_is_next_day_draft(context.user_id, chat_id=context.chat_id, now=now):
            self.checkins.upsert_goal_draft(context.user_id, draft_date, goals, chat_id=context.chat_id)
            return (
                f"<b>📝 Goals drafted — {h(context.display_name)}</b>\n"
                f"<i>For {short_date(draft_date)}</i>\n"
                f"{DIVIDER}\n"
                + "\n".join(goal_lines(goals))
                + "\n\nSend <code>/goals</code> again tonight to overwrite this draft. "
                "Tomorrow, send <code>/confirmgoals</code> to make it official, or send fresh <code>/goals</code> to replace it."
            )
        late = now.time().hour >= 10 and not self.participants.has_registration_grace(
            context.user_id,
            checkin_date,
            chat_id=context.chat_id,
        )
        late = self.checkins.upsert_goals(context.user_id, checkin_date, goals, late=late, chat_id=context.chat_id)
        late_note = "\n\n⚠️ <b>Late:</b> marked late because this was after 10:00am." if late else ""
        return (
            f"<b>✅ Goals recorded — {h(context.display_name)}</b>\n"
            f"<i>{short_date(checkin_date)}</i>{late_note}\n"
            f"{DIVIDER}\n"
            + "\n".join(goal_lines(goals))
        )

    def confirm_goals(self, context: MessageContext) -> str:
        checkin_date = self.today()
        late = datetime.now(SGT).time().hour >= 10 and not self.participants.has_registration_grace(
            context.user_id, checkin_date, chat_id=context.chat_id
        )
        goals = self.checkins.promote_goal_draft(context.user_id, checkin_date, late=late, chat_id=context.chat_id)
        if goals is None:
            return (
                "<b>📝 No draft to confirm</b>\n"
                f"{DIVIDER}\n"
                "Send <code>/goals</code> with 3 bullet lines to record today's goals."
            )
        late_note = "\n\n⚠️ <b>Late:</b> marked late because this was after 10:00am." if late else ""
        return (
            f"<b>✅ Draft confirmed — {h(context.display_name)}</b>\n"
            f"<i>{short_date(checkin_date)}</i>{late_note}\n"
            f"{DIVIDER}\n"
            + "\n".join(goal_lines(goals))
        )

    def report_done(self, command: ReportDoneInput | None) -> str:
        if command is None:
            return (
                "<b>🌙 Report completed goals</b>\n"
                f"{DIVIDER}\n"
                "Use one of these commands: <code>/done 0</code>, <code>/done 1</code>, "
                "<code>/done 2</code>, or <code>/done 3</code>."
            )
        context = command.context
        checkin_date = self.current_checkin_date()
        self.checkins.upsert_completion(context.user_id, checkin_date, command.completed_count, chat_id=context.chat_id)
        passed = command.completed_count >= 2
        result = "✅ Pass" if passed else "❌ Fail"
        encouragement = (
            "Nice — 2/3 or better keeps the day green."
            if passed
            else "Reset tomorrow — log goals early and aim for 2/3."
        )
        draft_prompt = (
            "\n\n<b>Plan ahead</b>\nSend <code>/goals</code> now to draft tomorrow's 3 goals."
            if command.completed_count == 3
            else ""
        )
        return (
            f"<b>{result} recorded — {h(context.display_name)}</b>\n"
            f"{DIVIDER}\n"
            f"Date: <b>{short_date(checkin_date)}</b>\n"
            f"Progress: <b>{command.completed_count}/3</b>\n\n"
            f"<i>{encouragement}</i>{draft_prompt}"
        )

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

    def amen(self) -> str:
        return self.content.amen()

    def buddha(self) -> str:
        return self.content.buddha()

    def angry(self) -> AnimationReply:
        return self.content.angry()
