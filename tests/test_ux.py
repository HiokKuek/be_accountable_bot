import pytest

from app.db import Database
from app.service import AccountabilityService
from app.telegram_client import TelegramClient
from app.telegram_updates import bot_was_added_to_chat


def make_service(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    return AccountabilityService(db)


def test_user_facing_text_does_not_show_markdown_heading_markers(tmp_path):
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    messages = [
        service.help_text(),
        service.rules_text(),
        service.morning_reminder(),
        service.today_summary(service.today(), chat_id=100),
        service.month_score(chat_id=100),
    ]
    assert all("##" not in message for message in messages)


def test_intro_text_explains_how_to_start(tmp_path):
    service = make_service(tmp_path)
    intro = service.intro_text()
    assert "Welcome" in intro
    assert "/register" in intro
    assert "/goals" in intro
    assert "/done" in intro
    assert "2/3" in intro


def test_command_menu_payload_lists_core_commands():
    commands = TelegramClient.command_menu()
    assert {item["command"] for item in commands} == {
        "register",
        "goals",
        "done",
        "today",
        "score",
        "rules",
        "help",
    }
    assert all(not item["command"].startswith("/") for item in commands)
    assert all(item["description"] for item in commands)


@pytest.mark.parametrize(
    "update,bot_id,expected",
    [
        ({"message": {"chat": {"id": -100}, "new_chat_members": [{"id": 42, "is_bot": True}]}}, 42, -100),
        ({"message": {"chat": {"id": -100}, "new_chat_members": [{"id": 7, "is_bot": True}]}}, 42, None),
        ({"message": {"chat": {"id": -100}, "new_chat_members": [{"id": 42, "is_bot": False}]}}, 42, None),
        ({"message": {"chat": {"id": -100}, "text": "/register"}}, 42, None),
    ],
)
def test_detects_when_this_bot_is_added_to_group(update, bot_id, expected):
    assert bot_was_added_to_chat(update, bot_id) == expected
