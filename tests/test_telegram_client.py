from app import telegram_client
from app.telegram_client import TelegramClient


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
