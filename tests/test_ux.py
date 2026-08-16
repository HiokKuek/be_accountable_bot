from pathlib import Path

import pytest

from app.repositories.db import Database
from app.services.accountability import AccountabilityService
from app.bot.telegram.telegram_client import TelegramClient
from app.bot.telegram.telegram_updates import bot_was_added_to_chat


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
    assert "Accountability Bot" in intro
    assert "group" in intro.lower()
    assert "group" in intro
    assert "/register" in intro
    assert "/goals" in intro
    assert "/done" in intro
    assert "2/3" in intro


def test_private_chat_intro_explains_bot_requires_group(tmp_path):
    service = make_service(tmp_path)
    intro = service.private_chat_text()

    assert "can't run in a private chat" in intro.lower()
    assert "group" in intro.lower()
    assert "group" in intro.lower()
    assert "/register" in intro


def test_command_menu_payload_lists_core_commands():
    commands = TelegramClient.command_menu()
    assert {item["command"] for item in commands} == {
        "register",
        "goals",
        "confirmgoals",
        "done",
        "today",
        "score",
        "remove",
        "rules",
        "help",
    }
    assert all(not item["command"].startswith("/") for item in commands)
    assert all(item["description"] for item in commands)


def test_hidden_buddha_command_does_not_leak_into_discovery_surfaces(tmp_path):
    service = make_service(tmp_path)
    discovery_surfaces = [
        (Path(__file__).parents[1] / "README.md").read_text(),
        service.intro_text(),
        service.help_text(),
        service.rules_text(),
        repr(TelegramClient.command_menu()),
    ]

    assert all("buddha" not in surface.lower() for surface in discovery_surfaces)


def test_hidden_angry_command_does_not_leak_into_discovery_surfaces(tmp_path):
    service = make_service(tmp_path)
    discovery_surfaces = [
        (Path(__file__).parents[1] / "README.md").read_text(),
        service.intro_text(),
        service.help_text(),
        service.rules_text(),
        service.private_chat_text(),
        repr(TelegramClient.command_menu()),
    ]

    assert all("angry" not in surface.lower() for surface in discovery_surfaces)


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
