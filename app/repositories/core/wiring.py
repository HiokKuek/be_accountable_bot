from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.repositories.checkins import CheckinRepository
from app.repositories.core.schema import SchemaRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.participants import ParticipantRepository


@dataclass(frozen=True)
class Repositories:
    schema: SchemaRepository
    participants: ParticipantRepository
    checkins: CheckinRepository
    notifications: NotificationRepository


def build_repositories(path: str | Path) -> Repositories:
    return Repositories(
        schema=SchemaRepository(path),
        participants=ParticipantRepository(path),
        checkins=CheckinRepository(path),
        notifications=NotificationRepository(path),
    )
