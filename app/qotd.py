from __future__ import annotations

from typing import Protocol

import httpx


DEFAULT_QOTD_API_URL = "https://zenquotes.io/api/today"


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
    ):
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def quote_of_the_day(self) -> tuple[str, str | None]:
        try:
            response = self.http_client.get(self.api_url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # httpx and JSON decoding failures
            raise QotdUnavailable("quote API request failed") from exc

        quote, author = self._parse_zenquotes_payload(payload)
        if not quote:
            raise QotdUnavailable("quote API returned no quote")
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
