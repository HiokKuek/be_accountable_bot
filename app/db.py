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

                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checkin_date TEXT NOT NULL,
                    telegram_user_id INTEGER NOT NULL REFERENCES users(telegram_user_id),
                    chat_id INTEGER,
                    goals_json TEXT,
                    goals_submitted_at TEXT,
                    goals_status TEXT NOT NULL DEFAULT 'missing_goals',
                    completed_count INTEGER,
                    completion_submitted_at TEXT,
                    result TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(checkin_date, telegram_user_id)
                );
                """
            )

    def register_chat(self, chat_id: int, title: str | None = None) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chats(chat_id, title, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title
                """,
                (chat_id, title, now),
            )

    def register_user(self, telegram_user_id: int, username: str | None, display_name: str) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
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

    def active_users(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT telegram_user_id, username, display_name FROM users WHERE active=1 ORDER BY registered_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def is_registered(self, telegram_user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE telegram_user_id=? AND active=1", (telegram_user_id,)
            ).fetchone()
        return row is not None

    def upsert_goals(self, telegram_user_id: int, checkin_date: date, goals: list[str], *, late: bool, chat_id: int | None = None) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        status = "late_submitted" if late else "submitted"
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT completed_count FROM checkins WHERE checkin_date=? AND telegram_user_id=?",
                (checkin_date.isoformat(), telegram_user_id),
            ).fetchone()
            completed = existing["completed_count"] if existing else None
            result = assess_day_result(goals_submitted=True, completed_count=completed)
            conn.execute(
                """
                INSERT INTO checkins(checkin_date, telegram_user_id, chat_id, goals_json, goals_submitted_at, goals_status, completed_count, result, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkin_date, telegram_user_id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    goals_json=excluded.goals_json,
                    goals_submitted_at=excluded.goals_submitted_at,
                    goals_status=excluded.goals_status,
                    result=excluded.result,
                    updated_at=excluded.updated_at
                """,
                (checkin_date.isoformat(), telegram_user_id, chat_id, json.dumps(goals), now, status, completed, result, now),
            )

    def upsert_completion(self, telegram_user_id: int, checkin_date: date, completed_count: int) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT goals_json FROM checkins WHERE checkin_date=? AND telegram_user_id=?",
                (checkin_date.isoformat(), telegram_user_id),
            ).fetchone()
            goals_submitted = bool(row and row["goals_json"])
            result = assess_day_result(goals_submitted=goals_submitted, completed_count=completed_count)
            conn.execute(
                """
                INSERT INTO checkins(checkin_date, telegram_user_id, completed_count, completion_submitted_at, result, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkin_date, telegram_user_id) DO UPDATE SET
                    completed_count=excluded.completed_count,
                    completion_submitted_at=excluded.completion_submitted_at,
                    result=excluded.result,
                    updated_at=excluded.updated_at
                """,
                (checkin_date.isoformat(), telegram_user_id, completed_count, now, result, now),
            )

    def get_checkin(self, telegram_user_id: int, checkin_date: date) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkins WHERE checkin_date=? AND telegram_user_id=?",
                (checkin_date.isoformat(), telegram_user_id),
            ).fetchone()
        return self._row_to_checkin(row) if row else None

    def checkins_for_day(self, checkin_date: date) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, u.username, u.display_name
                FROM checkins c
                JOIN users u ON u.telegram_user_id=c.telegram_user_id
                WHERE c.checkin_date=?
                ORDER BY u.registered_at
                """,
                (checkin_date.isoformat(),),
            ).fetchall()
        return [self._row_to_checkin(row) for row in rows]

    def close_day(self, checkin_date: date) -> None:
        now = datetime.now(SGT).isoformat(timespec="seconds")
        with self.connect() as conn:
            users = conn.execute("SELECT telegram_user_id FROM users WHERE active=1").fetchall()
            for user in users:
                uid = user["telegram_user_id"]
                row = conn.execute(
                    "SELECT goals_json, completed_count FROM checkins WHERE checkin_date=? AND telegram_user_id=?",
                    (checkin_date.isoformat(), uid),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO checkins(checkin_date, telegram_user_id, goals_status, result, updated_at)
                        VALUES (?, ?, 'missing_goals', 'fail', ?)
                        """,
                        (checkin_date.isoformat(), uid, now),
                    )
                    continue
                goals_submitted = bool(row["goals_json"])
                result = assess_day_result(goals_submitted=goals_submitted, completed_count=row["completed_count"])
                goals_status = "missing_goals" if not goals_submitted else None
                if goals_status:
                    conn.execute(
                        "UPDATE checkins SET goals_status=?, result=?, updated_at=? WHERE checkin_date=? AND telegram_user_id=?",
                        (goals_status, result, now, checkin_date.isoformat(), uid),
                    )
                else:
                    conn.execute(
                        "UPDATE checkins SET result=?, updated_at=? WHERE checkin_date=? AND telegram_user_id=?",
                        (result, now, checkin_date.isoformat(), uid),
                    )

    def failed_days_for_month(self, year: int, month: int) -> dict[str, int]:
        prefix = f"{year:04d}-{month:02d}-"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.display_name, COUNT(c.id) AS failed_days
                FROM users u
                LEFT JOIN checkins c
                  ON c.telegram_user_id=u.telegram_user_id
                 AND c.checkin_date LIKE ?
                 AND c.result='fail'
                WHERE u.active=1
                GROUP BY u.telegram_user_id
                ORDER BY u.registered_at
                """,
                (prefix + "%",),
            ).fetchall()
        return {row["display_name"]: row["failed_days"] for row in rows}

    def missing_goal_users(self, checkin_date: date) -> list[dict]:
        return self._missing_users(checkin_date, "goals")

    def missing_completion_users(self, checkin_date: date) -> list[dict]:
        return self._missing_users(checkin_date, "completion")

    def _missing_users(self, checkin_date: date, field: str) -> list[dict]:
        condition = "c.goals_json IS NULL" if field == "goals" else "c.completed_count IS NULL"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT u.telegram_user_id, u.username, u.display_name
                FROM users u
                LEFT JOIN checkins c ON c.telegram_user_id=u.telegram_user_id AND c.checkin_date=?
                WHERE u.active=1 AND ({condition})
                ORDER BY u.registered_at
                """,
                (checkin_date.isoformat(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_chat_id(self) -> int | None:
        with self.connect() as conn:
            row = conn.execute("SELECT chat_id FROM chats ORDER BY created_at DESC LIMIT 1").fetchone()
        return int(row["chat_id"]) if row else None

    def _row_to_checkin(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["goals"] = json.loads(data.pop("goals_json")) if data.get("goals_json") else None
        return data
