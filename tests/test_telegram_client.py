import asyncio

from app.bot.telegram import telegram_client
from app.bot.telegram.telegram_client import TelegramClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSyncClient:
    requests = []

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.requests.append((url, json))
        if url.endswith("/sendMessage"):
            return FakeResponse({"ok": True, "result": {"message_id": 123}})
        return FakeResponse({"ok": True, "result": True})


class FakeAsyncClient:
    requests = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.requests.append((url, json))
        return FakeResponse({"ok": True, "result": {"message_id": 456}})


def test_send_message_returns_message_id(monkeypatch):
    FakeSyncClient.requests = []
    monkeypatch.setattr(telegram_client.httpx, "Client", FakeSyncClient)
    client = TelegramClient("TOKEN")

    message_id = client.send_message_sync(100, "hello")

    assert message_id == 123


def test_pin_chat_message_posts_to_telegram_api(monkeypatch):
    FakeSyncClient.requests = []
    monkeypatch.setattr(telegram_client.httpx, "Client", FakeSyncClient)
    client = TelegramClient("TOKEN")

    assert client.pin_chat_message_sync(100, 123) is True

    assert FakeSyncClient.requests[-1] == (
        "https://api.telegram.org/botTOKEN/pinChatMessage",
        {"chat_id": 100, "message_id": 123, "disable_notification": True},
    )


def test_send_animation_posts_media_without_caption_by_default(monkeypatch):
    FakeAsyncClient.requests = []
    monkeypatch.setattr(telegram_client.httpx, "AsyncClient", FakeAsyncClient)
    client = TelegramClient("TOKEN")

    message_id = asyncio.run(client.send_animation(100, "https://example.com/angry.gif"))

    assert message_id == 456
    assert FakeAsyncClient.requests == [
        (
            "https://api.telegram.org/botTOKEN/sendAnimation",
            {
                "chat_id": 100,
                "animation": "https://example.com/angry.gif",
            },
        )
    ]


def test_send_animation_includes_caption_when_provided(monkeypatch):
    FakeAsyncClient.requests = []
    monkeypatch.setattr(telegram_client.httpx, "AsyncClient", FakeAsyncClient)
    client = TelegramClient("TOKEN")

    message_id = asyncio.run(
        client.send_animation(100, "https://example.com/angry.gif", "<b>Angry</b> &amp; safe")
    )

    assert message_id == 456
    assert FakeAsyncClient.requests == [
        (
            "https://api.telegram.org/botTOKEN/sendAnimation",
            {
                "chat_id": 100,
                "animation": "https://example.com/angry.gif",
                "caption": "<b>Angry</b> &amp; safe",
                "parse_mode": "HTML",
            },
        )
    ]


def test_send_animation_is_disabled_without_token():
    client = TelegramClient("")

    assert asyncio.run(client.send_animation(100, "https://example.com/angry.gif", "angry")) is None
