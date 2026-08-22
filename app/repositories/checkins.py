from __future__ import annotations

import json
from datetime import date, datetime

from app.domain.rules import assess_day_result
from app.repositories.core.db import SGT, SQLiteRepository


class CheckinRepository(SQLiteRepository):
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
            existing_on_time = bool(existing and existing["goals_json"] and existing["goals_status"] == "submitted")
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
