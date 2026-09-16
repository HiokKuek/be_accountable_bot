from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.repositories.core.wiring import Repositories, build_repositories
from app.services.accountability import AccountabilityService
from app.services.content import ContentService
from app.services.reminders import ReminderService
from app.services.summaries import SummaryService


@dataclass(frozen=True)
class TestEnv:
    repositories: Repositories
    accountability: AccountabilityService
    summaries: SummaryService
    reminders: ReminderService
    content: ContentService


def build_env(
    path: str | Path,
    *,
    penalty_amount: int = 5,
    qotd_client=None,
    bible_verse_client=None,
    buddha_quote_client=None,
    angry_gif_client=None,
) -> TestEnv:
    repositories = build_repositories(path)
    repositories.schema.init()
    content = ContentService(
        qotd_client=qotd_client,
        bible_verse_client=bible_verse_client,
        buddha_quote_client=buddha_quote_client,
        angry_gif_client=angry_gif_client,
    )
    accountability = AccountabilityService(
        repositories.participants,
        repositories.checkins,
        repositories.notifications,
        penalty_amount=penalty_amount,
        content=content,
    )
    summaries = SummaryService(repositories.checkins, content, penalty_amount=penalty_amount)
    reminders = ReminderService(repositories.checkins, summaries)
    return TestEnv(
        repositories=repositories,
        accountability=accountability,
        summaries=summaries,
        reminders=reminders,
        content=content,
    )
