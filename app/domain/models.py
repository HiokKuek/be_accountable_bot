from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageContext:
    user_id: int
    username: str | None
    display_name: str
    chat_id: int
    chat_type: str | None = None
    chat_title: str | None = None


@dataclass(frozen=True)
class SubmitGoalsInput:
    context: MessageContext
    goals: list[str]


@dataclass(frozen=True)
class ReportDoneInput:
    context: MessageContext
    completed_count: int
