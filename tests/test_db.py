from datetime import date

from app.db import Database


def test_register_and_list_active_users(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    users = db.active_users(chat_id=100)
    assert users == [{"telegram_user_id": 1, "username": "ernest", "display_name": "Ernest"}]


def test_upsert_goals_and_completion(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    day = date(2026, 7, 8)
    db.upsert_goals(1, day, ["invest", "intervals", "read"], late=False, chat_id=100)
    db.upsert_completion(1, day, 2, chat_id=100)
    row = db.get_checkin(1, day, chat_id=100)
    assert row["goals"] == ["invest", "intervals", "read"]
    assert row["completed_count"] == 2
    assert row["result"] == "pass"


def test_close_day_marks_missing_goals_and_missing_completion_as_fail(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    db.register_user(2, "friend", "Friend", chat_id=100)
    day = date(2026, 7, 8)
    db.upsert_goals(1, day, ["invest", "intervals", "read"], late=False, chat_id=100)
    db.close_day(day, chat_id=100)
    rows = db.checkins_for_day(day, chat_id=100)
    by_user = {r["telegram_user_id"]: r for r in rows}
    assert by_user[1]["result"] == "fail"
    assert by_user[2]["result"] == "fail"
    assert by_user[2]["goals_status"] == "missing_goals"


def test_same_telegram_user_has_separate_checkins_per_group(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    db.register_user(1, "ernest", "Ernest", chat_id=200)
    day = date(2026, 7, 8)

    db.upsert_goals(1, day, ["group 100 a", "group 100 b", "group 100 c"], late=False, chat_id=100)
    db.upsert_completion(1, day, 3, chat_id=100)
    db.upsert_goals(1, day, ["group 200 a", "group 200 b", "group 200 c"], late=False, chat_id=200)
    db.upsert_completion(1, day, 1, chat_id=200)

    group_100 = db.get_checkin(1, day, chat_id=100)
    group_200 = db.get_checkin(1, day, chat_id=200)

    assert group_100["goals"] == ["group 100 a", "group 100 b", "group 100 c"]
    assert group_100["result"] == "pass"
    assert group_200["goals"] == ["group 200 a", "group 200 b", "group 200 c"]
    assert group_200["result"] == "fail"


def test_delete_user_by_name_removes_group_membership_and_checkins(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "remove_me", "Remove Me", chat_id=100)
    db.register_user(2, "ernest", "Ernest", chat_id=100)
    day = date(2026, 7, 8)
    db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    db.upsert_completion(1, day, 3, chat_id=100)

    deleted = db.delete_user_by_name("remove_me")

    assert deleted == 1
    assert [u["display_name"] for u in db.active_users(chat_id=100)] == ["Ernest"]
    assert db.get_checkin(1, day, chat_id=100) is None
