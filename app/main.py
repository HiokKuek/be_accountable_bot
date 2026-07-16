from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request

from app.db import Database
from app.scheduler import build_scheduler
from app.service import AccountabilityService
from app.parsing import parse_goals
from app.qotd import QotdApiClient
from app.settings import Settings
from app.telegram_client import TelegramClient
from app.telegram_updates import bot_was_added_to_chat

settings = Settings()
db = Database(settings.database_path)
qotd_client = QotdApiClient(api_url=settings.qotd_api_url)
service = AccountabilityService(db, penalty_amount=settings.penalty_amount, qotd_client=qotd_client)
telegram = TelegramClient(settings.telegram_bot_token)
scheduler = build_scheduler(service, telegram)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    await telegram.initialize()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Accountability Bot", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "timezone": settings.timezone,
        "webhook_path": settings.webhook_path,
        "telegram_configured": telegram.enabled(),
        "telegram_bot_id_known": telegram.bot_id is not None,
    }


@app.post(settings.webhook_path)
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
        db.register_chat(int(added_chat_id), chat.get("title"))
        await telegram.send_message(int(added_chat_id), service.intro_text())
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    text = message.get("text")
    if not text:
        return {"ok": True}

    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = sender.get("id")
    if chat_id is None or user_id is None:
        return {"ok": True}

    first = sender.get("first_name") or ""
    last = sender.get("last_name") or ""
    display_name = (first + " " + last).strip() or sender.get("username") or str(user_id)
    username = sender.get("username")
    chat_title = chat.get("title")
    chat_type = chat.get("type")

    if chat_type == "private":
        response = service.handle_text(int(user_id), username, display_name, int(chat_id), text, chat_type=chat_type)
        if response:
            await telegram.send_message(int(chat_id), response)
        return {"ok": True}

    db.register_chat(int(chat_id), chat_title)

    parsed_goals = parse_goals(text)
    routes_to_draft = parsed_goals is not None and service.goal_submission_is_next_day_draft(
        int(user_id), chat_id=int(chat_id)
    )
    confirms_draft = text.strip().lower().startswith("/confirmgoals") and db.get_goal_draft(
        int(user_id), service.today(), chat_id=int(chat_id)
    ) is not None
    response = service.handle_text(int(user_id), username, display_name, int(chat_id), text, chat_type=chat_type)
    if response:
        await telegram.send_message(int(chat_id), response)

    official_goals_command = (parsed_goals is not None and not routes_to_draft) or confirms_draft
    if chat_type != "private" and official_goals_command:
        checkin_date = service.today()
        if db.all_active_users_have_goals(checkin_date, chat_id=int(chat_id)) and db.claim_notification_once(
            "goals-keyed", checkin_date, chat_id=int(chat_id)
        ):
            message_id = await telegram.send_message(int(chat_id), service.goal_confirmation_summary(checkin_date, chat_id=int(chat_id)))
            if message_id is not None:
                await telegram.pin_chat_message(int(chat_id), message_id)
    return {"ok": True}
