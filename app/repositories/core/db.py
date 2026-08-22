from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.repositories.checkins import CheckinRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.participants import ParticipantRepository
from app.repositories.core.schema import SchemaRepository


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


class Database:
    def __init__(self, path: str | Path):
        self.repositories = build_repositories(path)
        self.schema = self.repositories.schema
        self.participants = self.repositories.participants
        self.checkins = self.repositories.checkins
        self.notifications = self.repositories.notifications

    @classmethod
    def from_repositories(
        cls,
        *,
        schema: SchemaRepository,
        participants: ParticipantRepository,
        checkins: CheckinRepository,
        notifications: NotificationRepository,
    ) -> "Database":
        database = cls.__new__(cls)
        database.repositories = Repositories(
            schema=schema,
            participants=participants,
            checkins=checkins,
            notifications=notifications,
        )
        database.schema = schema
        database.participants = participants
        database.checkins = checkins
        database.notifications = notifications
        return database

    def connect(self):
        return self.schema.connect()

    def init(self) -> None:
        self.schema.init()

    def __getattr__(self, name: str):
        for repository in (self.schema, self.participants, self.checkins, self.notifications):
            if hasattr(repository, name):
                return getattr(repository, name)
        raise AttributeError(name)
