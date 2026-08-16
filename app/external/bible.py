from __future__ import annotations

from typing import Protocol

import httpx


DEFAULT_BIBLE_VERSE_API_URL = "https://bible-api.com/?random=verse"


class BibleVerseUnavailable(RuntimeError):
    """Raised when the Bible API cannot provide a usable verse."""


class BibleVerseClient(Protocol):
    def random_verse(self) -> tuple[str, str]:
        """Return verse text and its reference from an external service."""
        ...


class BibleVerseApiClient:
    def __init__(
        self,
        *,
        api_url: str = DEFAULT_BIBLE_VERSE_API_URL,
        timeout_seconds: float = 5.0,
        http_client: httpx.Client | None = None,
    ):
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def random_verse(self) -> tuple[str, str]:
        try:
            response = self.http_client.get(self.api_url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # httpx and JSON decoding failures
            raise BibleVerseUnavailable("Bible verse API request failed") from exc

        return self._parse_payload(payload)

    def _parse_payload(self, payload: object) -> tuple[str, str]:
        if not isinstance(payload, dict):
            raise BibleVerseUnavailable("Bible verse API returned an unexpected response")

        text = payload.get("text")
        reference = payload.get("reference")
        if not isinstance(text, str) or not text.strip():
            raise BibleVerseUnavailable("Bible verse API returned no verse text")
        if not isinstance(reference, str) or not reference.strip():
            raise BibleVerseUnavailable("Bible verse API returned no reference")

        return text.strip(), reference.strip()
