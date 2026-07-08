from __future__ import annotations

import httpx


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}" if token else ""

    def enabled(self) -> bool:
        return bool(self.token)

    async def send_message(self, chat_id: int, text: str) -> None:
        if not self.enabled():
            return
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()

    def send_message_sync(self, chat_id: int, text: str) -> None:
        if not self.enabled():
            return
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
