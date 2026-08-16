from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.clients.bible import DEFAULT_BIBLE_VERSE_API_URL
from app.clients.qotd import DEFAULT_QOTD_API_URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""
    webhook_secret: str = ""
    public_base_url: str = "https://accountability.hiok.dev"
    database_path: Path = Path("/data/accountability.sqlite3")
    penalty_amount: int = 5
    timezone: str = "Asia/Singapore"
    qotd_api_url: str = DEFAULT_QOTD_API_URL
    bible_verse_api_url: str = DEFAULT_BIBLE_VERSE_API_URL
    tenor_api_key: str = ""

    @property
    def webhook_path(self) -> str:
        return "/telegram/webhook"

    @property
    def webhook_url(self) -> str:
        return self.public_base_url.rstrip("/") + self.webhook_path
