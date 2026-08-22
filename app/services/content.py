from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.repositories.angry import AngryGifClient, AngryGifProvider
from app.repositories.bible import BibleVerseApiClient, BibleVerseClient, BibleVerseUnavailable
from app.repositories.buddha import BuddhaQuoteClient, BuddhaQuoteUnavailable, LocalBuddhaQuoteClient
from app.repositories.qotd import QotdApiClient, QotdClient, QotdUnavailable


def h(value: object) -> str:
    return escape(str(value), quote=False)


@dataclass(frozen=True)
class AnimationReply:
    animation: str
    caption: str | None = None


class ContentService:
    def __init__(
        self,
        *,
        qotd_client: QotdClient | None = None,
        bible_verse_client: BibleVerseClient | None = None,
        buddha_quote_client: BuddhaQuoteClient | None = None,
        angry_gif_client: AngryGifProvider | None = None,
    ):
        self.qotd_client = qotd_client or QotdApiClient()
        self.bible_verse_client = bible_verse_client or BibleVerseApiClient()
        self.buddha_quote_client = buddha_quote_client or LocalBuddhaQuoteClient()
        self.angry_gif_client = angry_gif_client or AngryGifClient()

    def angry(self) -> AnimationReply:
        reaction = self.angry_gif_client.random_reaction()
        return AnimationReply(animation=reaction.url)

    def qotd(self) -> str:
        try:
            quote, author = self.qotd_client.quote_of_the_day()
        except QotdUnavailable:
            return "<b>💬 QOTD</b>\n<blockquote><i>Quote temporarily unavailable.</i></blockquote>"

        lines = ["<b>💬 QOTD</b>", f"<blockquote><i>{h(quote)}</i></blockquote>"]
        if author:
            lines.append(f"— {h(author)}")
        return "\n".join(lines)

    def amen(self) -> str:
        try:
            verse, reference = self.bible_verse_client.random_verse()
        except BibleVerseUnavailable:
            return "<b>🙏 Amen</b>\n<blockquote><i>Verse temporarily unavailable.</i></blockquote>"

        return f"<b>🙏 Amen</b>\n<blockquote>{h(verse)}</blockquote>\n— <b>{h(reference)}</b>"

    def buddha(self) -> str:
        try:
            quote, category = self.buddha_quote_client.random_quote()
        except BuddhaQuoteUnavailable:
            return "<b>☸️ Buddha</b>\n<blockquote><i>Reflection temporarily unavailable.</i></blockquote>"

        return (
            "<b>☸️ Buddha</b>\n"
            f"<i>Original reflection · {h(category.replace('_', ' ').title())}</i>\n"
            f"<blockquote>{h(quote)}</blockquote>"
        )
