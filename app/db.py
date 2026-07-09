from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.domain import assess_day_result

SGT = ZoneInfo("Asia/Singapore")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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

                CREATE TABLE IF NOT EXISTS notifications (
                    chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                    notification_date TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, notification_date, kind)
                );
                """
            )
            self._ensure_group_scoped_checkins(conn)
            self._backfill_participants(conn)

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

    def _create_checkins_table(self, conn: sqlite3.Connection, table_name: str) -> None:
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

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
        return row is not None

    def _has_group_scoped_checkins_index(self, conn: sqlite3.Connection) -> bool:
        for index in conn.execute("PRAGMA index_list(checkins)").fetchall():
            if not index["unique"]:
                continue
            columns = [row["name"] for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()]
            if columns == ["checkin_date", "chat_id", "telegram_user_id"]:
                return True
        return False

    def _default_chat_id_for_migration(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT chat_id FROM chats ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            return int(row["chat_id"])
        now = datetime.now(SGT).isoformat(timespec="seconds")
        conn.execute("INSERT OR IGNORE INTO chats(chat_id, title, created_at) VALUES (?, ?, ?)", (0, "Migrated default chat", now))
        return 0

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
                ON CONFLICT(chat_id, telegram_user_id) DO UPDATE SET active=1
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

    def upsert_goals(self, telegram_user_id: int, checkin_date: date, goals: list[str], *, late: bool, chat_id: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        status = "late_submitted" if late else "submitted"
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT completed_count FROM checkins WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?",
                (checkin_date.isoformat(), chat_id, telegram_user_id),
            ).fetchone()
            completed = existing["completed_count"] if existing else None
            result = assess_day_result(goals_submitted=True, completed_count=completed) if completed is not None else None
            conn.execute(
                """
                INSERT INTO checkins(checkin_date, chat_id, telegram_user_id, goals_json, goals_submitted_at, goals_status, completed_count, result, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkin_date, chat_id, telegram_user_id) DO UPDATE SET
                    goals_json=excluded.goals_json,
                    goals_submitted_at=excluded.goals_submitted_at,
                    goals_status=excluded.goals_status,
                    result=excluded.result,
                    updated_at=excluded.updated_at
                """,
                (checkin_date.isoformat(), chat_id, telegram_user_id, json.dumps(goals), now, status, completed, result, now),
            )

    def upsert_completion(self, telegram_user_id: int, checkin_date: date, completed_count: int, *, chat_id: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT goals_json FROM checkins WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?",
                (checkin_date.isoformat(), chat_id, telegram_user_id),
            ).fetchone()
            goals_submitted = bool(row and row["goals_json"])
            result = assess_day_result(goals_submitted=goals_submitted, completed_count=completed_count)
            conn.execute(
                """
                INSERT INTO checkins(checkin_date, chat_id, telegram_user_id, completed_count, completion_submitted_at, result, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkin_date, chat_id, telegram_user_id) DO UPDATE SET
                    completed_count=excluded.completed_count,
                    completion_submitted_at=excluded.completion_submitted_at,
                    result=excluded.result,
                    updated_at=excluded.updated_at
                """,
                (checkin_date.isoformat(), chat_id, telegram_user_id, completed_count, now, result, now),
            )

    def get_checkin(self, telegram_user_id: int, checkin_date: date, *, chat_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkins WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?",
                (checkin_date.isoformat(), chat_id, telegram_user_id),
            ).fetchone()
        return self._row_to_checkin(row) if row else None

    def checkins_for_day(self, checkin_date: date, *, chat_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, u.telegram_user_id AS roster_telegram_user_id, u.username, u.display_name
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=? AND p.active=1 AND u.active=1
                ORDER BY p.registered_at
                """,
                (checkin_date.isoformat(), chat_id),
            ).fetchall()
        return [self._row_to_checkin(row) for row in rows]

    def close_day(self, checkin_date: date, *, chat_id: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            users = conn.execute(
                """
                SELECT p.telegram_user_id
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                WHERE p.chat_id=? AND p.active=1 AND u.active=1
                """,
                (chat_id,),
            ).fetchall()
            for user in users:
                uid = user["telegram_user_id"]
                row = conn.execute(
                    "SELECT goals_json, completed_count FROM checkins WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?",
                    (checkin_date.isoformat(), chat_id, uid),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO checkins(checkin_date, chat_id, telegram_user_id, goals_status, result, updated_at)
                        VALUES (?, ?, ?, 'missing_goals', 'fail', ?)
                        """,
                        (checkin_date.isoformat(), chat_id, uid, now),
                    )
                    continue
                goals_submitted = bool(row["goals_json"])
                result = assess_day_result(goals_submitted=goals_submitted, completed_count=row["completed_count"])
                goals_status = "missing_goals" if not goals_submitted else None
                if goals_status:
                    conn.execute(
                        "UPDATE checkins SET goals_status=?, result=?, updated_at=? WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?",
                        (goals_status, result, now, checkin_date.isoformat(), chat_id, uid),
                    )
                else:
                    conn.execute(
                        "UPDATE checkins SET result=?, updated_at=? WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?",
                        (result, now, checkin_date.isoformat(), chat_id, uid),
                    )

    def failed_days_for_month(self, year: int, month: int, *, chat_id: int) -> dict[str, int]:
        prefix = f"{year:04d}-{month:02d}-"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.display_name, COUNT(c.id) AS failed_days
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date LIKE ?
                 AND c.result='fail'
                WHERE p.chat_id=? AND p.active=1 AND u.active=1
                GROUP BY p.chat_id, p.telegram_user_id
                ORDER BY p.registered_at
                """,
                (prefix + "%", chat_id),
            ).fetchall()
        return {row["display_name"]: row["failed_days"] for row in rows}

    def missing_goal_users(self, checkin_date: date, *, chat_id: int) -> list[dict]:
        return self._missing_users(checkin_date, "goals", chat_id=chat_id)

    def missing_completion_users(self, checkin_date: date, *, chat_id: int) -> list[dict]:
        return self._missing_users(checkin_date, "completion", chat_id=chat_id)

    def all_active_users_have_goals(self, checkin_date: date, *, chat_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS missing_count
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=? AND p.active=1 AND u.active=1 AND c.goals_json IS NULL
                """,
                (checkin_date.isoformat(), chat_id),
            ).fetchone()
        return int(row["missing_count"]) == 0

    def claim_notification_once(self, kind: str, notification_date: date, *, chat_id: int) -> bool:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO chats(chat_id, title, created_at) VALUES (?, NULL, ?)", (chat_id, now))
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO notifications(chat_id, notification_date, kind, sent_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, notification_date.isoformat(), kind, now),
            )
            return cursor.rowcount == 1

    def _missing_users(self, checkin_date: date, field: str, *, chat_id: int) -> list[dict]:
        condition = "c.goals_json IS NULL" if field == "goals" else "c.completed_count IS NULL"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT u.telegram_user_id, u.username, u.display_name
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=? AND p.active=1 AND u.active=1 AND ({condition})
                ORDER BY p.registered_at
                """,
                (checkin_date.isoformat(), chat_id),
            ).fetchall()
        return [dict(row) for row in rows]

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
                ORDER BY c.created_at
                """
            ).fetchall()
        return [int(row["chat_id"]) for row in rows]

    def delete_user_by_name(self, name: str) -> int:
        normalized = name.strip().casefold()
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

    def _row_to_checkin(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["goals"] = json.loads(data.pop("goals_json")) if data.get("goals_json") else None
        return data
