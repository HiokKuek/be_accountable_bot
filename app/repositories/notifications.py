from __future__ import annotations

from datetime import date, datetime

from app.repositories.core.base import SGT, SQLiteRepository


class NotificationRepository(SQLiteRepository):
    def claim_notification_once(self, kind: str, notification_date: date, *, chat_id: int) -> bool:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chats(chat_id, title, created_at) VALUES (?, NULL, ?)", (chat_id, now))
            existing = conn.execute(
                """
                SELECT 1 FROM notification_events
                WHERE chat_id=? AND notification_date=? AND kind=? AND status='sent'
                LIMIT 1
                """,
                (chat_id, notification_date.isoformat(), kind),
            ).fetchone()
            if existing:
                return False
            cursor = conn.execute(
                """
                INSERT INTO notification_events(
                    chat_id, notification_date, kind, status, message_id, error, sent_at
                )
                VALUES (?, ?, ?, 'sent', NULL, NULL, ?)
                """,
                (chat_id, notification_date.isoformat(), kind, now),
            )
            return cursor.rowcount == 1

    def record_notification_event(
        self,
        kind: str,
        notification_date: date,
        *,
        chat_id: int,
        status: str = "sent",
        message_id: int | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chats(chat_id, title, created_at) VALUES (?, NULL, ?)", (chat_id, now))
            conn.execute(
                """
                INSERT INTO notification_events(
                    chat_id, notification_date, kind, status, message_id, error, sent_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, notification_date.isoformat(), kind, status, message_id, error, now),
            )

    def notification_events_for_day(self, notification_date: date, *, chat_id: int | None = None) -> list[dict]:
        params: list[object] = [notification_date.isoformat()]
        where = "notification_date=?"
        if chat_id is not None:
            where += " AND chat_id=?"
            params.append(chat_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chat_id, notification_date, kind, status, message_id, error, sent_at
                FROM notification_events
                WHERE {where}
                ORDER BY sent_at, id
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]
