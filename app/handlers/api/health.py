from __future__ import annotations

from fastapi import APIRouter

from app.config import Settings
from app.handlers.telegram.response_mapper import TelegramClient


def build_health_router(settings: Settings, telegram: TelegramClient) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "timezone": settings.timezone,
            "webhook_path": settings.webhook_path,
            "telegram_configured": telegram.enabled(),
            "telegram_bot_id_known": telegram.bot_id is not None,
        }

    return router
