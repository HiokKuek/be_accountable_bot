from __future__ import annotations

from datetime import date, datetime

from app.repositories.core.base import SGT, SQLiteRepository


class ParticipantRepository(SQLiteRepository):
    def register_chat(self, chat_id: int, title: str | None = None) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chats(chat_id, title, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET title=COALESCE(excluded.title, chats.title)
                """,
                (chat_id, title, now),
            )

    def register_user(self, telegram_user_id: int, username: str | None, display_name: str, *, chat_id: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chats(chat_id, title, created_at) VALUES (?, NULL, ?)", (chat_id, now))
            conn.execute(
                """
                INSERT INTO users(telegram_user_id, username, display_name, active, registered_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    username=excluded.username,
                    display_name=excluded.display_name,
                    active=1
                """,
                (telegram_user_id, username, display_name, now),
            )
            conn.execute(
                """
                INSERT INTO participants(chat_id, telegram_user_id, active, registered_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(chat_id, telegram_user_id) DO UPDATE SET
                    registered_at=CASE
                        WHEN participants.active=0 THEN excluded.registered_at
                        ELSE participants.registered_at
                    END,
                    active=1
                """,
                (chat_id, telegram_user_id, now),
            )

    def active_users(self, *, chat_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.telegram_user_id, u.username, u.display_name
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                WHERE p.chat_id=? AND p.active=1 AND u.active=1
                ORDER BY p.registered_at
                """,
                (chat_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def is_registered(self, telegram_user_id: int, *, chat_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                WHERE p.chat_id=? AND p.telegram_user_id=? AND p.active=1 AND u.active=1
                """,
                (chat_id, telegram_user_id),
            ).fetchone()
        return row is not None

    def has_registration_grace(self, telegram_user_id: int, checkin_date: date, *, chat_id: int) -> bool:
        deadline, next_day = self._goal_deadline_bounds(checkin_date)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                WHERE p.chat_id=?
                  AND p.telegram_user_id=?
                  AND p.active=1
                  AND u.active=1
                  AND p.registered_at > ?
                  AND p.registered_at < ?
                """,
                (chat_id, telegram_user_id, deadline, next_day),
            ).fetchone()
        return row is not None

    def latest_chat_id(self) -> int | None:
        with self.connect() as conn:
            row = conn.execute("SELECT chat_id FROM chats ORDER BY created_at DESC LIMIT 1").fetchone()
        return int(row["chat_id"]) if row else None

    def active_chat_ids(self) -> list[int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.chat_id
                FROM chats c
                JOIN participants p ON p.chat_id=c.chat_id AND p.active=1
                WHERE c.chat_id < 0
                ORDER BY c.created_at
                """
            ).fetchall()
        return [int(row["chat_id"]) for row in rows]

    def delete_user_by_name(self, name: str) -> int:
        normalized = name.strip().lstrip("@").casefold()
        if not normalized:
            return 0
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT telegram_user_id
                FROM users
                WHERE lower(COALESCE(username, ''))=? OR lower(display_name)=?
                """,
                (normalized, normalized),
            ).fetchall()
            user_ids = [int(row["telegram_user_id"]) for row in rows]
            if not user_ids:
                return 0
            placeholders = ",".join("?" for _ in user_ids)
            conn.execute(f"DELETE FROM checkins WHERE telegram_user_id IN ({placeholders})", user_ids)
            conn.execute(f"DELETE FROM participants WHERE telegram_user_id IN ({placeholders})", user_ids)
            conn.execute(f"DELETE FROM users WHERE telegram_user_id IN ({placeholders})", user_ids)
        return len(user_ids)

    def deactivate_participant_by_name(self, chat_id: int, name: str) -> dict | None:
        normalized = name.strip().lstrip("@").casefold()
        if not normalized:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT u.telegram_user_id, u.display_name
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                WHERE p.chat_id=?
                  AND p.active=1
                  AND u.active=1
                  AND (lower(COALESCE(u.username, ''))=? OR lower(u.display_name)=?)
                ORDER BY p.registered_at
                LIMIT 1
                """,
                (chat_id, normalized, normalized),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE participants SET active=0 WHERE chat_id=? AND telegram_user_id=?",
                (chat_id, row["telegram_user_id"]),
            )
        return {"telegram_user_id": int(row["telegram_user_id"]), "display_name": row["display_name"]}
