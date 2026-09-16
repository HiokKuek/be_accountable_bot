from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.handlers.api.health import build_health_router
from app.handlers.api.telegram_webhook import build_telegram_webhook_router
from app.handlers.scheduler.daily_jobs import build_scheduler
from app.handlers.telegram.response_mapper import TelegramClient
from app.repositories.angry import AngryGifClient
from app.repositories.bible import BibleVerseApiClient
from app.repositories.core.wiring import build_repositories
from app.repositories.qotd import QotdApiClient
from app.services.accountability import AccountabilityService
from app.services.content import ContentService
from app.services.reminders import ReminderService
from app.services.summaries import SummaryService

settings = Settings()
repositories = build_repositories(settings.database_path)
content = ContentService(
    qotd_client=QotdApiClient(api_url=settings.qotd_api_url),
    bible_verse_client=BibleVerseApiClient(api_url=settings.bible_verse_api_url),
    angry_gif_client=AngryGifClient(tenor_api_key=settings.tenor_api_key),
)
accountability = AccountabilityService(
    repositories.participants,
    repositories.checkins,
    repositories.notifications,
    penalty_amount=settings.penalty_amount,
    content=content,
)
summaries = SummaryService(repositories.checkins, content, penalty_amount=settings.penalty_amount)
reminders = ReminderService(repositories.checkins, summaries)
telegram = TelegramClient(settings.telegram_bot_token)
scheduler = build_scheduler(reminders, summaries, telegram, repositories.participants, repositories.notifications)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repositories.schema.init()
    await telegram.initialize()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Accountability Bot", lifespan=lifespan)
app.include_router(build_health_router(settings, telegram))
app.include_router(
    build_telegram_webhook_router(
        settings,
        telegram,
        repositories.participants,
        repositories.checkins,
        repositories.notifications,
        accountability,
        summaries,
    )
)
