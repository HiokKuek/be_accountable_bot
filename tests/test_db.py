from datetime import date

from app.db import Database


def test_register_and_list_active_users(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest")
    users = db.active_users()
    assert users == [{"telegram_user_id": 1, "username": "ernest", "display_name": "Ernest"}]


def test_upsert_goals_and_completion(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest")
    day = date(2026, 7, 8)
    db.upsert_goals(1, day, ["invest", "intervals", "read"], late=False)
    db.upsert_completion(1, day, 2)
    row = db.get_checkin(1, day)
    assert row["goals"] == ["invest", "intervals", "read"]
    assert row["completed_count"] == 2
    assert row["result"] == "pass"


def test_close_day_marks_missing_goals_and_missing_completion_as_fail(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest")
    db.register_user(2, "friend", "Friend")
    day = date(2026, 7, 8)
    db.upsert_goals(1, day, ["invest", "intervals", "read"], late=False)
    db.close_day(day)
    rows = db.checkins_for_day(day)
    by_user = {r["telegram_user_id"]: r for r in rows}
    assert by_user[1]["result"] == "fail"
    assert by_user[2]["result"] == "fail"
    assert by_user[2]["goals_status"] == "missing_goals"
