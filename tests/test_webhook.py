from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.handlers.api.telegram_webhook import build_telegram_webhook_router
from tests.conftest import build_env


class FakeTelegram:
    def __init__(self):
        self.bot_id = 42
        self.sent = []
        self.animations = []

    async def send_message(self, chat_id: int, text: str):
        self.sent.append((chat_id, text))
        return 9000 + len(self.sent)

    async def send_animation(self, chat_id: int, animation: str, caption: str | None = None):
        self.animations.append((chat_id, animation, caption))
        return 8000 + len(self.animations)


class FakeChatSummarise:
    def __init__(self):
        self.captured = []
        self.calls = []

    def capture_message(self, context, text: str):
        self.captured.append((context.chat_id, text))

    async def summarise(self, context):
        self.calls.append(context.chat_id)
        return "<b>summary</b>"


def make_update(text: str, *, user_id: int = 1, chat_id: int = -100, chat_type: str = "group"):
    return {
        "message": {
            "chat": {"id": chat_id, "type": chat_type, "title": "Focus Group"},
            "from": {"id": user_id, "username": "ernest", "first_name": "Ernest"},
            "text": text,
        }
    }


def build_client(tmp_path, env=None):
    env = env or build_env(tmp_path / "test.sqlite3")
    telegram = FakeTelegram()
    chat_summarise = FakeChatSummarise()
    settings = Settings(webhook_secret="", telegram_bot_token="")
    app = FastAPI()
    app.include_router(
        build_telegram_webhook_router(
            settings,
            telegram,
            env.repositories.participants,
            env.repositories.checkins,
            env.repositories.notifications,
            env.accountability,
            env.summaries,
            chat_summarise,
        )
    )
    return TestClient(app), telegram, chat_summarise


def test_plain_group_chat_text_is_captured_but_not_replied_to(tmp_path):
    client, telegram, chat_summarise = build_client(tmp_path)

    response = client.post("/telegram/webhook", json=make_update("hello team"))

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert telegram.sent == []
    assert chat_summarise.captured == [(-100, "hello team")]


def test_summarise_command_replies_without_requiring_registration(tmp_path):
    client, telegram, chat_summarise = build_client(tmp_path)

    client.post("/telegram/webhook", json=make_update("earlier message"))
    response = client.post("/telegram/webhook", json=make_update("/summarise"))

    assert response.status_code == 200
    assert telegram.sent[-1] == (-100, "<b>summary</b>")
    assert chat_summarise.calls == [-100]
    assert chat_summarise.captured == [(-100, "earlier message")]


def test_confirmgoals_still_records_early_summary_message_for_later_pin(tmp_path):
    env = build_env(tmp_path / "test.sqlite3")
    day = env.accountability.today()
    env.repositories.participants.register_user(1, "cyril", "Cyril", chat_id=-100)
    env.repositories.participants.register_user(2, "ernest", "Ernest", chat_id=-100)
    with env.repositories.schema.connect() as conn:
        conn.execute(
            "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
            (f"{day.isoformat()}T09:00:00+08:00", -100, 1),
        )
        conn.execute(
            "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
            (f"{day.isoformat()}T09:00:00+08:00", -100, 2),
        )
    env.repositories.checkins.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=-100)
    env.repositories.checkins.upsert_goal_draft(2, day, ["d", "e", "f"], chat_id=-100)
    client, telegram, _ = build_client(tmp_path, env=env)

    response = client.post("/telegram/webhook", json=make_update("/confirmgoals", user_id=2))

    assert response.status_code == 200
    assert len(telegram.sent) == 2
    assert "Draft confirmed" in telegram.sent[0][1]
    assert "All goals are keyed" in telegram.sent[1][1]
    assert env.repositories.notifications.goal_summary_message_id(day, chat_id=-100) == 9002
