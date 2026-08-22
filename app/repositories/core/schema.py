from __future__ import annotations

import sqlite3
from datetime import datetime

from app.repositories.core.db import SGT, SQLiteRepository


class SchemaRepository(SQLiteRepository):
    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    registered_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS participants (
                    chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                    telegram_user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
                    active INTEGER NOT NULL DEFAULT 1,
                    registered_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, telegram_user_id)
                );
                """
            )
            self._ensure_notification_events(conn)
            self._ensure_group_scoped_checkins(conn)
            self._ensure_goal_drafts(conn)
            self._backfill_participants(conn)

    @staticmethod
    def _ensure_goal_drafts(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_drafts (
                draft_date TEXT NOT NULL,
                chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                telegram_user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
                goals_json TEXT NOT NULL,
                drafted_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(draft_date, chat_id, telegram_user_id)
            )
            """
        )

    def _ensure_notification_events(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                notification_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                message_id INTEGER,
                error TEXT,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notification_events_day_chat_kind
            ON notification_events(notification_date, chat_id, kind)
            """
        )
        conn.execute("DROP INDEX IF EXISTS idx_notification_events_unique_sent")
        if not self._table_exists(conn, "notifications"):
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO notification_events(
                chat_id, notification_date, kind, status, message_id, error, sent_at
            )
            SELECT chat_id, notification_date, kind, 'sent', NULL, NULL, sent_at
            FROM notifications
            """
        )
        conn.execute("DROP TABLE notifications")

    def _ensure_group_scoped_checkins(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "checkins"):
            self._create_checkins_table(conn, "checkins")
            return
        if self._has_group_scoped_checkins_index(conn):
            return

        default_chat_id = self._default_chat_id_for_migration(conn)
        self._create_checkins_table(conn, "checkins_new")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(checkins)").fetchall()}
        chat_expr = "COALESCE(chat_id, ?)" if "chat_id" in columns else "?"
        conn.execute(
            f"""
            INSERT OR IGNORE INTO checkins_new(
                id,
                checkin_date,
                chat_id,
                telegram_user_id,
                goals_json,
                goals_submitted_at,
                goals_status,
                completed_count,
                completion_submitted_at,
                result,
                updated_at
            )
            SELECT
                id,
                checkin_date,
                {chat_expr},
                telegram_user_id,
                goals_json,
                goals_submitted_at,
                goals_status,
                completed_count,
                completion_submitted_at,
                result,
                updated_at
            FROM checkins
            """,
            (default_chat_id,),
        )
        conn.execute("DROP TABLE checkins")
        conn.execute("ALTER TABLE checkins_new RENAME TO checkins")

    @staticmethod
    def _create_checkins_table(conn: sqlite3.Connection, table_name: str) -> None:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkin_date TEXT NOT NULL,
                chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                telegram_user_id INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
                goals_json TEXT,
                goals_submitted_at TEXT,
                goals_status TEXT NOT NULL DEFAULT 'missing_goals',
                completed_count INTEGER,
                completion_submitted_at TEXT,
                result TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(checkin_date, chat_id, telegram_user_id)
            )
            """
        )

    def _backfill_participants(self, conn: sqlite3.Connection) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        chat_count = conn.execute("SELECT COUNT(*) AS count FROM chats").fetchone()["count"]
        if chat_count == 1:
            chat_id = conn.execute("SELECT chat_id FROM chats LIMIT 1").fetchone()["chat_id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO participants(chat_id, telegram_user_id, active, registered_at)
                SELECT ?, telegram_user_id, active, registered_at FROM users WHERE active=1
                """,
                (chat_id,),
            )
        conn.execute(
            """
            INSERT OR IGNORE INTO participants(chat_id, telegram_user_id, active, registered_at)
            SELECT DISTINCT c.chat_id, c.telegram_user_id, 1, ?
            FROM checkins c
            """,
            (now,),
        )
