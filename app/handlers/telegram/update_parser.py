from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import MessageContext

_DONE_RE = re.compile(r"^/done(?:@\w+)?\s+([0-3])\s*$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-*•]\s*")
_NUMBERED_MARKER_RE = re.compile(r"^\d+[.)]\s+")


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    context: MessageContext
    text: str
    goals: list[str] | None = None
    completed_count: int | None = None
    argument: str | None = None


@dataclass(frozen=True)
class ParsedTextMessage:
    context: MessageContext
    text: str


def parse_done_count(text: str) -> int | None:
    match = _DONE_RE.match(text.strip())
    if not match:
        return None
    return int(match.group(1))


def parse_goals(text: str) -> list[str] | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None

    first = lines[0].lower()
    if not (first.startswith("/goals") or "checkins" in first):
        return None

    goals: list[str] = []
    for line in lines[1:]:
        cleaned = _BULLET_RE.sub("", line, count=1).strip()
        cleaned = _NUMBERED_MARKER_RE.sub("", cleaned, count=1).strip()
        if cleaned:
            goals.append(cleaned)
    return goals if len(goals) == 3 else None


def bot_was_added_to_chat(update: dict, bot_id: int | None) -> int | None:
    if bot_id is None:
        return None
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    for member in message.get("new_chat_members") or []:
        if member.get("is_bot") and member.get("id") == bot_id:
            return int(chat_id)
    return None


def parse_text_message(update: dict) -> ParsedTextMessage | None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None

    text = message.get("text")
    if not text:
        return None

    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = sender.get("id")
    if chat_id is None or user_id is None:
        return None

    first = sender.get("first_name") or ""
    last = sender.get("last_name") or ""
    display_name = (first + " " + last).strip() or sender.get("username") or str(user_id)
    context = MessageContext(
        user_id=int(user_id),
        username=sender.get("username"),
        display_name=display_name,
        chat_id=int(chat_id),
        chat_type=chat.get("type"),
        chat_title=chat.get("title"),
    )
    return ParsedTextMessage(context=context, text=text)


def parse_command(update: dict) -> ParsedCommand | None:
    parsed_text = parse_text_message(update)
    if parsed_text is None:
        return None

    context = parsed_text.context
    stripped = parsed_text.text.strip()
    goals = parse_goals(stripped)
    if not stripped.startswith("/") and goals is None:
        return None

    command = stripped.split(maxsplit=1)[0].lower().split("@", maxsplit=1)[0]
    if not command.startswith("/") and goals is not None:
        command = "/goals"
    done_count = parse_done_count(stripped)
    argument = None
    if command == "/remove":
        parts = stripped.split(maxsplit=1)
        if len(parts) > 1:
            argument = parts[1]
    return ParsedCommand(
        name=command,
        context=context,
        text=stripped,
        goals=goals,
        completed_count=done_count,
        argument=argument,
    )
