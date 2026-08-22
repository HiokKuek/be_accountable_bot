from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SGT = ZoneInfo("Asia/Singapore")


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
        return row is not None

    @staticmethod
    def _has_group_scoped_checkins_index(conn: sqlite3.Connection) -> bool:
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

    @staticmethod
    def _goal_deadline_bounds(checkin_date: date) -> tuple[str, str]:
        deadline = datetime.combine(checkin_date, time(10, 0), tzinfo=SGT)
        next_day = datetime.combine(checkin_date + timedelta(days=1), time(0, 0), tzinfo=SGT)
        return deadline.isoformat(timespec="seconds"), next_day.isoformat(timespec="seconds")

    @staticmethod
    def _row_to_checkin(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["goals"] = json.loads(data.pop("goals_json")) if data.get("goals_json") else None
        return data
