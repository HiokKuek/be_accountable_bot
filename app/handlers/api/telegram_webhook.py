from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.domain.models import ReportDoneInput, SubmitGoalsInput
from app.handlers.telegram.response_mapper import TelegramClient, TelegramResponseMapper
from app.handlers.telegram.update_parser import bot_was_added_to_chat, parse_command
from app.repositories.checkins import CheckinRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.participants import ParticipantRepository
from app.services.accountability import AccountabilityService
from app.services.summaries import SummaryService
from app.config import Settings


def build_telegram_webhook_router(
    settings: Settings,
    telegram: TelegramClient,
    participants: ParticipantRepository,
    checkins: CheckinRepository,
    notifications: NotificationRepository,
    accountability: AccountabilityService,
    summaries: SummaryService,
) -> APIRouter:
    router = APIRouter()
    mapper = TelegramResponseMapper(telegram)

    @router.post(settings.webhook_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

        update = await request.json()

        added_chat_id = bot_was_added_to_chat(update, telegram.bot_id)
        if added_chat_id is not None:
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            participants.register_chat(int(added_chat_id), chat.get("title"))
            await mapper.send_reply(int(added_chat_id), accountability.intro_text())
            return {"ok": True}

        parsed = parse_command(update)
        if parsed is None:
            return {"ok": True}

        context = parsed.context
        if context.chat_type == "private":
            await mapper.send_reply(context.chat_id, accountability.private_chat_text())
            return {"ok": True}

        participants.register_chat(context.chat_id, context.chat_title)

        if parsed.name == "/register":
            response = accountability.register_participant(context)
        elif parsed.name == "/rules":
            response = accountability.rules_text()
        elif parsed.name == "/help":
            response = accountability.help_text()
        elif parsed.name == "/amen":
            response = accountability.amen()
        elif parsed.name == "/buddha":
            response = accountability.buddha()
        elif parsed.name == "/angry":
            response = accountability.angry()
        elif not participants.is_registered(context.user_id, chat_id=context.chat_id):
            response = accountability.registration_required()
        elif parsed.name == "/remove":
            response = accountability.remove_participant(context, parsed.argument)
        elif parsed.goals is not None:
            response = accountability.submit_goals(SubmitGoalsInput(context=context, goals=parsed.goals))
        elif parsed.name == "/goals":
            response = accountability.goals_usage_text()
        elif parsed.name == "/confirmgoals":
            response = accountability.confirm_goals(context)
        elif parsed.name == "/done":
            response = accountability.report_done(
                ReportDoneInput(context=context, completed_count=parsed.completed_count)
                if parsed.completed_count is not None
                else None
            )
        elif parsed.name == "/today":
            response = summaries.today_summary(accountability.current_checkin_date(), chat_id=context.chat_id)
        elif parsed.name in {"/score", "/summary"}:
            response = summaries.month_score(chat_id=context.chat_id)
        else:
            response = None

        await mapper.send_reply(context.chat_id, response)

        confirms_draft = parsed.name == "/confirmgoals" and checkins.get_goal_draft(
            context.user_id, accountability.today(), chat_id=context.chat_id
        ) is not None
        official_goals_command = (parsed.goals is not None and not accountability.goal_submission_is_next_day_draft(
            context.user_id, chat_id=context.chat_id
        )) or confirms_draft
        if official_goals_command:
            checkin_date = accountability.today()
            if checkins.all_active_users_have_goals(checkin_date, chat_id=context.chat_id) and notifications.claim_notification_once(
                "goals-keyed", checkin_date, chat_id=context.chat_id
            ):
                message_id = await mapper.send_reply(
                    context.chat_id,
                    summaries.goal_confirmation_summary(checkin_date, chat_id=context.chat_id),
                )
                if message_id is not None:
                    await telegram.pin_chat_message(context.chat_id, message_id)
        return {"ok": True}

    return router
