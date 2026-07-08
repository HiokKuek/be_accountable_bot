from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request

from app.db import Database
from app.scheduler import build_scheduler
from app.service import AccountabilityService
from app.settings import Settings
from app.telegram_client import TelegramClient

settings = Settings()
db = Database(settings.database_path)
service = AccountabilityService(db, penalty_amount=settings.penalty_amount)
telegram = TelegramClient(settings.telegram_bot_token)
scheduler = build_scheduler(service, telegram)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
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
    }


@app.post(settings.webhook_path)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    update = await request.json()
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
    db.register_chat(int(chat_id), chat_title)

    response = service.handle_text(int(user_id), username, display_name, int(chat_id), text)
    if response:
        await telegram.send_message(int(chat_id), response)
    return {"ok": True}
