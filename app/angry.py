from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

import httpx


TENOR_SEARCH_URL = "https://tenor.googleapis.com/v2/search"


@dataclass(frozen=True)
class AngryReaction:
    url: str
    caption: str


LOCAL_ANGRY_REACTIONS = (
    AngryReaction(
        "https://media.giphy.com/media/11tTNkNy1SdXGg/giphy.gif",
        "When the goals are still not done. 😤",
    ),
    AngryReaction(
        "https://media.giphy.com/media/l1J9u3TZfpmeDLkD6/giphy.gif",
        "Accountability mode: aggressively activated.",
    ),
    AngryReaction(
        "https://media.giphy.com/media/3o9bJX4O9ShW1L32eY/giphy.gif",
        "That look when someone says “I forgot my goals.”",
    ),
)


class AngryGifProvider(Protocol):
    def random_reaction(self) -> AngryReaction:
        """Return an angry reaction GIF and caption."""
        ...


class LocalAngryGifProvider:
    def random_reaction(self) -> AngryReaction:
        return random.choice(LOCAL_ANGRY_REACTIONS)


class AngryGifClient:
    def __init__(
        self,
        *,
        tenor_api_key: str = "",
        http_client: httpx.Client | None = None,
        fallback: AngryGifProvider | None = None,
    ):
        self.tenor_api_key = tenor_api_key
        self.http_client = http_client or httpx.Client(timeout=5)
        self.fallback = fallback or LocalAngryGifProvider()

    def random_reaction(self) -> AngryReaction:
        if not self.tenor_api_key:
            return self.fallback.random_reaction()

        try:
            response = self.http_client.get(
                TENOR_SEARCH_URL,
                params={
                    "q": "angry reaction",
                    "key": self.tenor_api_key,
                    "client_key": "accountability_bot",
                    "limit": 10,
                    "media_filter": "gif",
                    "contentfilter": "high",
                    "random": "true",
                },
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list) or not results:
                raise ValueError("Tenor returned no results")
            item = random.choice(results)
            url = item["media_formats"]["gif"]["url"]
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError("Tenor returned an invalid GIF URL")
            return AngryReaction(url, "Accountability rage activated. 😤")
        except Exception:
            return self.fallback.random_reaction()
