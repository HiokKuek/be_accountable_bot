from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}" if token else ""
        self.bot_id: int | None = None

    def enabled(self) -> bool:
        return bool(self.token)

    @staticmethod
    def command_menu() -> list[dict[str, str]]:
        return [
            {"command": "register", "description": "Join the accountability challenge"},
            {"command": "goals", "description": "Submit today's 3 goals"},
            {"command": "done", "description": "Report completed goals: /done 0-3"},
            {"command": "today", "description": "Show today's status"},
            {"command": "score", "description": "Show this month's settlement"},
            {"command": "rules", "description": "Show the challenge rules"},
            {"command": "help", "description": "Show examples and commands"},
        ]

    async def initialize(self) -> None:
        if not self.enabled():
            return
        try:
            self.bot_id = await self.get_me_id()
            await self.set_my_commands()
        except Exception:
            logger.exception("Telegram client initialization failed")

    async def get_me_id(self) -> int | None:
        if not self.enabled():
            return None
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/getMe")
            response.raise_for_status()
            payload = response.json()
        result = payload.get("result") or {}
        bot_id = result.get("id")
        return int(bot_id) if bot_id is not None else None

    async def set_my_commands(self) -> None:
        if not self.enabled():
            return
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/setMyCommands",
                json={"commands": self.command_menu()},
            )
            response.raise_for_status()

    async def send_message(self, chat_id: int, text: str) -> None:
        if not self.enabled():
            return
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
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
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
