from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

import httpx


DEFAULT_QOTD_API_URL = "https://zenquotes.io/api/today"
SGT = ZoneInfo("Asia/Singapore")


@dataclass(frozen=True)
class CachedQotd:
    day: date
    quote: str
    author: str | None


class QotdUnavailable(RuntimeError):
    """Raised when the quote API cannot provide a usable quote."""


class QotdClient(Protocol):
    def quote_of_the_day(self) -> tuple[str, str | None]:
        """Return a quote and optional author from an external service."""
        ...


class QotdApiClient:
    def __init__(
        self,
        *,
        api_url: str = DEFAULT_QOTD_API_URL,
        timeout_seconds: float = 5.0,
        http_client: httpx.Client | None = None,
        today_provider: Callable[[], date] | None = None,
    ):
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self.today_provider = today_provider or (lambda: datetime.now(SGT).date())
        self._cached_qotd: CachedQotd | None = None

    def quote_of_the_day(self) -> tuple[str, str | None]:
        today = self.today_provider()
        if self._cached_qotd is not None and self._cached_qotd.day == today:
            return self._cached_qotd.quote, self._cached_qotd.author

        try:
            response = self.http_client.get(self.api_url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # httpx and JSON decoding failures
            raise QotdUnavailable("quote API request failed") from exc

        quote, author = self._parse_zenquotes_payload(payload)
        if not quote:
            raise QotdUnavailable("quote API returned no quote")
        self._cached_qotd = CachedQotd(day=today, quote=quote, author=author)
        return quote, author

    def _parse_zenquotes_payload(self, payload: object) -> tuple[str, str | None]:
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise QotdUnavailable("quote API returned an unexpected response")

        item = payload[0]
        quote = item.get("q")
        author = item.get("a")
        if not isinstance(quote, str) or not quote.strip():
            raise QotdUnavailable("quote API returned no quote")
        if not isinstance(author, str) or not author.strip() or author.strip().lower() == "unknown":
            author = None
        return quote.strip(), author.strip() if author else None
