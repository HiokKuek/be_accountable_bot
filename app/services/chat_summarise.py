from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from html import escape
import re
from zoneinfo import ZoneInfo

from app.domain.models import MessageContext
from app.repositories.openrouter import OpenRouterClient, OpenRouterUnavailable

SGT = ZoneInfo("Asia/Singapore")
DIVIDER = "━━━━━━━━━━━━"
DEFAULT_SUMMARISE_BUFFER_SIZE = 100
SUMMARY_SECTIONS = ("TL;DR", "Topics", "Action items", "Open questions")
SECTION_PATTERNS = {
    "TL;DR": re.compile(r"(?is)\bTL;DR\s*:+\s*(.*?)(?=\b(?:TL;DR|Topics|Action items?|Open questions?)\s*:+|\Z)"),
    "Topics": re.compile(r"(?is)\bTopics\s*:+\s*(.*?)(?=\b(?:TL;DR|Topics|Action items?|Open questions?)\s*:+|\Z)"),
    "Action items": re.compile(r"(?is)\bAction items?\s*:+\s*(.*?)(?=\b(?:TL;DR|Topics|Action items?|Open questions?)\s*:+|\Z)"),
    "Open questions": re.compile(r"(?is)\bOpen questions?\s*:+\s*(.*?)(?=\b(?:TL;DR|Topics|Action items?|Open questions?)\s*:+|\Z)"),
}


def h(value: object) -> str:
    return escape(str(value), quote=False)


@dataclass(frozen=True)
class CapturedChatMessage:
    display_name: str
    text: str
    created_at: datetime


class ChatMessageBuffer:
    def __init__(self, per_chat_limit: int = DEFAULT_SUMMARISE_BUFFER_SIZE):
        self.per_chat_limit = per_chat_limit
        self._messages: dict[int, deque[CapturedChatMessage]] = defaultdict(
            lambda: deque(maxlen=self.per_chat_limit)
        )

    def record(self, context: MessageContext, text: str, *, now: datetime | None = None) -> None:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return
        self._messages[context.chat_id].append(
            CapturedChatMessage(
                display_name=context.display_name,
                text=cleaned,
                created_at=now or datetime.now(SGT),
            )
        )

    def recent_messages(self, chat_id: int, *, limit: int | None = None) -> list[CapturedChatMessage]:
        messages = list(self._messages.get(chat_id, ()))
        if limit is None or limit >= len(messages):
            return messages
        return messages[-limit:]

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = " ".join(text.split())
        return cleaned[:500].strip()


class ChatSummariseService:
    def __init__(
        self,
        client: OpenRouterClient,
        buffer: ChatMessageBuffer,
        *,
        max_messages: int = DEFAULT_SUMMARISE_BUFFER_SIZE,
    ):
        self.client = client
        self.buffer = buffer
        self.max_messages = max_messages

    def capture_message(self, context: MessageContext, text: str) -> None:
        self.buffer.record(context, text)

    async def summarise(self, context: MessageContext) -> str:
        messages = self.buffer.recent_messages(context.chat_id, limit=self.max_messages)
        if not messages:
            return (
                "<b>🧠 Chat summary unavailable</b>\n"
                f"{DIVIDER}\n"
                "I don't have any recent messages cached for this chat yet. "
                "I can only summarise messages I've seen since the bot started."
            )
        if not self.client.enabled():
            return (
                "<b>🧠 /summarise is not configured</b>\n"
                f"{DIVIDER}\n"
                "Add <code>OPENROUTER_API_KEY</code> and <code>OPENROUTER_MODEL</code> to the bot's <code>.env</code>, "
                "then restart the bot."
            )
        try:
            summary = await self.client.summarize_messages(self._build_prompt(context, messages))
        except OpenRouterUnavailable as exc:
            return (
                "<b>🧠 Chat summary temporarily unavailable</b>\n"
                f"{DIVIDER}\n"
                f"{h(exc)}"
            )
        normalized_summary = self._normalize_summary(summary)
        return (
            "<b>🧠 Chat Summary</b>\n"
            f"<i>Based on the last {len(messages)} captured messages.</i>\n"
            f"{DIVIDER}\n"
            f"{h(normalized_summary)}"
        )

    def _build_prompt(self, context: MessageContext, messages: list[CapturedChatMessage]) -> str:
        transcript = "\n".join(self._format_message(message) for message in messages)
        chat_name = context.chat_title or f"chat {context.chat_id}"
        return (
            "Summarise this Telegram group conversation.\n"
            "Keep it useful for the participants.\n"
            "Use exactly these sections in plain text:\n"
            "TL;DR:\n"
            "Topics:\n"
            "Action items:\n"
            "Open questions:\n"
            "Use short bullet points under each section. If a section has nothing, write '- None'.\n"
            "Do not mention messages that are not in the transcript.\n\n"
            f"Chat: {chat_name}\n"
            f"Messages provided: {len(messages)}\n\n"
            "Transcript:\n"
            f"{transcript}"
        )

    @staticmethod
    def _format_message(message: CapturedChatMessage) -> str:
        timestamp = message.created_at.astimezone(SGT).strftime("%H:%M")
        return f"[{timestamp}] {message.display_name}: {message.text}"

    def _normalize_summary(self, summary: str) -> str:
        cleaned = summary.strip()
        sections = self._extract_sections(cleaned)
        if not any(items for items in sections.values()):
            fallback = self._clean_items(cleaned)
            sections["TL;DR"] = fallback or ["None"]
        rendered: list[str] = []
        for title in SUMMARY_SECTIONS:
            rendered.append(f"{title}:")
            items = sections[title] or ["None"]
            rendered.extend(f"- {item}" for item in items)
            if title != SUMMARY_SECTIONS[-1]:
                rendered.append("")
        return "\n".join(rendered).strip()

    def _extract_sections(self, summary: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {title: [] for title in SUMMARY_SECTIONS}
        for title, pattern in SECTION_PATTERNS.items():
            matches = pattern.findall(summary)
            for chunk in reversed(matches):
                items = self._clean_items(chunk)
                if items:
                    sections[title] = items
                    break
        return sections

    @staticmethod
    def _clean_items(raw: str) -> list[str]:
        text = raw.strip()
        if not text:
            return []
        text = text.replace("\r", "")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        items: list[str] = []
        for line in lines:
            line = re.sub(r"^(?:[-*•]+|\d+[.)])\s*", "", line).strip()
            if not line:
                continue
            lower = line.lower()
            if any(
                phrase in lower
                for phrase in (
                    "here's a thinking process",
                    "analyze user request",
                    "analyse user request",
                    "analyze the transcript",
                    "analyse the transcript",
                    "extract key information",
                    "map to required sections",
                    "output only",
                    "the user wants",
                    "let's analyze",
                    "let us analyze",
                    "i need to produce",
                    "do not reveal reasoning",
                    "plain text only",
                )
            ):
                continue
            line = re.sub(r"^(?:TL;DR|Topics|Action items?|Open questions?)\s*:+\s*", "", line, flags=re.I)
            line = re.sub(r"\s+", " ", line).strip(" -:\t")
            if not line:
                continue
            parts = [part.strip(" -:\t") for part in re.split(r"\s*[;•]\s*", line) if part.strip(" -:\t")]
            items.extend(parts)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped
