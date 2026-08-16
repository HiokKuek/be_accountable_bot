from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.logic.rules import assess_day_result

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

                """
            )
            self._ensure_notification_events(conn)
            self._ensure_group_scoped_checkins(conn)
            self._ensure_goal_drafts(conn)
            self._backfill_participants(conn)

    def _ensure_goal_drafts(self, conn: sqlite3.Connection) -> None:
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

    def upsert_goals(self, telegram_user_id: int, checkin_date: date, goals: list[str], *, late: bool, chat_id: int) -> bool:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        status = "late_submitted" if late else "submitted"
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT goals_json, goals_submitted_at, goals_status, completed_count
                FROM checkins
                WHERE checkin_date=? AND chat_id=? AND telegram_user_id=?
                """,
                (checkin_date.isoformat(), chat_id, telegram_user_id),
            ).fetchone()
            existing_on_time = bool(
                existing and existing["goals_json"] and existing["goals_status"] == "submitted"
            )
            if existing_on_time:
                status = "submitted"
                submitted_at = existing["goals_submitted_at"]
            else:
                submitted_at = now
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
                (
                    checkin_date.isoformat(),
                    chat_id,
                    telegram_user_id,
                    json.dumps(goals),
                    submitted_at,
                    status,
                    completed,
                    result,
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM goal_drafts WHERE draft_date=? AND chat_id=? AND telegram_user_id=?",
                (checkin_date.isoformat(), chat_id, telegram_user_id),
            )
        return status == "late_submitted"

    def upsert_goal_draft(self, telegram_user_id: int, draft_date: date, goals: list[str], *, chat_id: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO goal_drafts(draft_date, chat_id, telegram_user_id, goals_json, drafted_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_date, chat_id, telegram_user_id) DO UPDATE SET
                    goals_json=excluded.goals_json,
                    drafted_at=excluded.drafted_at,
                    updated_at=excluded.updated_at
                """,
                (draft_date.isoformat(), chat_id, telegram_user_id, json.dumps(goals), now, now),
            )

    def get_goal_draft(self, telegram_user_id: int, draft_date: date, *, chat_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT draft_date, chat_id, telegram_user_id, goals_json, drafted_at, updated_at
                FROM goal_drafts
                WHERE draft_date=? AND chat_id=? AND telegram_user_id=?
                """,
                (draft_date.isoformat(), chat_id, telegram_user_id),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["goals"] = json.loads(data.pop("goals_json"))
        return data

    def promote_goal_draft(self, telegram_user_id: int, draft_date: date, *, late: bool, chat_id: int) -> list[str] | None:
        draft = self.get_goal_draft(telegram_user_id, draft_date, chat_id=chat_id)
        if draft is None:
            return None
        goals = draft["goals"]
        self.upsert_goals(telegram_user_id, draft_date, goals, late=late, chat_id=chat_id)
        return goals

    def draft_goal_users(self, draft_date: date, *, chat_id: int) -> list[dict]:
        deadline, next_day = self._goal_deadline_bounds(draft_date)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.telegram_user_id, u.username, u.display_name
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                JOIN goal_drafts d
                  ON d.telegram_user_id=p.telegram_user_id
                 AND d.chat_id=p.chat_id
                 AND d.draft_date=?
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=?
                  AND p.active=1
                  AND u.active=1
                  AND c.goals_json IS NULL
                  AND NOT (p.registered_at > ? AND p.registered_at < ?)
                ORDER BY p.registered_at
                """,
                (draft_date.isoformat(), draft_date.isoformat(), chat_id, deadline, next_day),
            ).fetchall()
        return [dict(row) for row in rows]

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
        deadline, next_day = self._goal_deadline_bounds(checkin_date)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, u.telegram_user_id AS roster_telegram_user_id, u.username, u.display_name, p.registered_at
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=?
                  AND p.active=1
                  AND u.active=1
                  AND (NOT (p.registered_at > ? AND p.registered_at < ?) OR c.goals_json IS NOT NULL)
                ORDER BY p.registered_at
                """,
                (checkin_date.isoformat(), chat_id, deadline, next_day),
            ).fetchall()
        return [self._row_to_checkin(row) for row in rows]

    def close_day(self, checkin_date: date, *, chat_id: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        deadline, next_day = self._goal_deadline_bounds(checkin_date)
        with self.connect() as conn:
            users = conn.execute(
                """
                SELECT p.telegram_user_id
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=?
                  AND p.active=1
                  AND u.active=1
                  AND (NOT (p.registered_at > ? AND p.registered_at < ?) OR c.goals_json IS NOT NULL)
                """,
                (checkin_date.isoformat(), chat_id, deadline, next_day),
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
        deadline, next_day = self._goal_deadline_bounds(checkin_date)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS active_count,
                    SUM(CASE WHEN c.goals_json IS NULL THEN 1 ELSE 0 END) AS missing_count
                FROM participants p
                JOIN users u ON u.telegram_user_id=p.telegram_user_id
                LEFT JOIN checkins c
                  ON c.telegram_user_id=p.telegram_user_id
                 AND c.chat_id=p.chat_id
                 AND c.checkin_date=?
                WHERE p.chat_id=?
                  AND p.active=1
                  AND u.active=1
                  AND NOT (p.registered_at > ? AND p.registered_at < ?)
                """,
                (checkin_date.isoformat(), chat_id, deadline, next_day),
            ).fetchone()
        return int(row["active_count"]) > 0 and int(row["missing_count"] or 0) == 0

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

    def _missing_users(self, checkin_date: date, field: str, *, chat_id: int) -> list[dict]:
        if field == "goals":
            condition = "c.goals_json IS NULL AND NOT (p.registered_at > ? AND p.registered_at < ?)"
        else:
            condition = "c.completed_count IS NULL AND (NOT (p.registered_at > ? AND p.registered_at < ?) OR c.goals_json IS NOT NULL)"
        deadline, next_day = self._goal_deadline_bounds(checkin_date)
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
                (checkin_date.isoformat(), chat_id, deadline, next_day),
            ).fetchall()
        return [dict(row) for row in rows]

    def _goal_deadline_bounds(self, checkin_date: date) -> tuple[str, str]:
        deadline = datetime.combine(checkin_date, time(10, 0), tzinfo=SGT)
        next_day = datetime.combine(checkin_date + timedelta(days=1), time(0, 0), tzinfo=SGT)
        return deadline.isoformat(timespec="seconds"), next_day.isoformat(timespec="seconds")

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

    def _row_to_checkin(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["goals"] = json.loads(data.pop("goals_json")) if data.get("goals_json") else None
        return data
