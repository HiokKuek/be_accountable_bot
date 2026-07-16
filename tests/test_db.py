from datetime import date
import sqlite3

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


def test_upsert_goals_preserves_existing_on_time_submission_status(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    day = date(2026, 7, 9)

    assert db.upsert_goals(1, day, ["first a", "first b", "first c"], late=False, chat_id=100) is False
    original = db.get_checkin(1, day, chat_id=100)

    assert db.upsert_goals(1, day, ["edited a", "edited b", "edited c"], late=True, chat_id=100) is False
    edited = db.get_checkin(1, day, chat_id=100)

    assert edited["goals"] == ["edited a", "edited b", "edited c"]
    assert edited["goals_status"] == "submitted"
    assert edited["goals_submitted_at"] == original["goals_submitted_at"]


def test_goal_drafts_are_overwriteable_group_scoped_and_cleared_by_official_goals(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    db.register_user(1, "ernest", "Ernest", chat_id=200)
    day = date(2026, 7, 10)

    db.upsert_goal_draft(1, day, ["first a", "first b", "first c"], chat_id=100)
    db.upsert_goal_draft(1, day, ["other a", "other b", "other c"], chat_id=200)
    db.upsert_goal_draft(1, day, ["new a", "new b", "new c"], chat_id=100)

    assert db.get_goal_draft(1, day, chat_id=100)["goals"] == ["new a", "new b", "new c"]
    assert db.get_goal_draft(1, day, chat_id=200)["goals"] == ["other a", "other b", "other c"]

    db.upsert_goals(1, day, ["official a", "official b", "official c"], late=False, chat_id=100)

    assert db.get_goal_draft(1, day, chat_id=100) is None
    assert db.get_goal_draft(1, day, chat_id=200) is not None


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


def test_close_day_does_not_fail_users_who_register_after_goal_deadline(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "late", "Late Joiner", chat_id=100)
    day = date(2026, 7, 9)
    with db.connect() as conn:
        conn.execute(
            "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
            ("2026-07-09T10:30:00+08:00", 100, 1),
        )

    assert db.missing_goal_users(day, chat_id=100) == []

    db.close_day(day, chat_id=100)

    assert db.get_checkin(1, day, chat_id=100) is None


def test_late_registered_users_count_for_completion_if_they_submit_grace_goals(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "late", "Late Joiner", chat_id=100)
    day = date(2026, 7, 9)
    with db.connect() as conn:
        conn.execute(
            "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
            ("2026-07-09T10:30:00+08:00", 100, 1),
        )
    db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)

    missing_completion = db.missing_completion_users(day, chat_id=100)

    assert [user["telegram_user_id"] for user in missing_completion] == [1]


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


def test_all_active_users_have_goals_for_day(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    day = date(2026, 7, 9)
    db.register_user(1, "cyril", "cyril", chat_id=100)
    db.register_user(2, "ernest", "Ernest", chat_id=100)
    db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)

    assert db.all_active_users_have_goals(day, chat_id=100) is False

    db.upsert_goals(2, day, ["d", "e", "f"], late=False, chat_id=100)

    assert db.all_active_users_have_goals(day, chat_id=100) is True


def test_claim_notification_once_is_group_and_day_scoped(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    day = date(2026, 7, 9)

    assert db.claim_notification_once("goals-keyed", day, chat_id=100) is True
    assert db.claim_notification_once("goals-keyed", day, chat_id=100) is False
    assert db.claim_notification_once("goals-keyed", day, chat_id=200) is True
    assert db.claim_notification_once("goals-keyed", date(2026, 7, 10), chat_id=100) is True

    events = db.notification_events_for_day(day, chat_id=100)
    assert [event["kind"] for event in events] == ["goals-keyed"]
    assert events[0]["status"] == "sent"


def test_init_merges_legacy_notifications_into_notification_events_and_drops_old_table(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE chats (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE notifications (
                chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                notification_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(chat_id, notification_date, kind)
            );
            INSERT INTO chats(chat_id, title, created_at)
            VALUES (-100, 'goals', '2026-07-09T08:00:00+08:00');
            INSERT INTO notifications(chat_id, notification_date, kind, sent_at)
            VALUES (-100, '2026-07-09', 'goals-keyed', '2026-07-09T09:31:00+08:00');
            """
        )

    db = Database(db_path)
    db.init()

    events = db.notification_events_for_day(date(2026, 7, 9), chat_id=-100)
    assert events == [
        {
            "chat_id": -100,
            "notification_date": "2026-07-09",
            "kind": "goals-keyed",
            "status": "sent",
            "message_id": None,
            "error": None,
            "sent_at": "2026-07-09T09:31:00+08:00",
        }
    ]
    with sqlite3.connect(db_path) as conn:
        legacy = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='notifications'").fetchone()
    assert legacy is None


def test_active_chat_ids_excludes_private_chats_from_scheduled_jobs(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=-100)
    db.register_user(2, "maverick", "Maverick", chat_id=647161028)

    assert db.active_chat_ids() == [-100]


def test_all_active_users_have_goals_requires_at_least_one_active_user(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()

    assert db.all_active_users_have_goals(date(2026, 7, 9), chat_id=-100) is False


def test_deactivate_participant_by_name_is_scoped_to_chat(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.register_user(1, "ernest", "Ernest", chat_id=100)
    db.register_user(1, "ernest", "Ernest", chat_id=200)

    removed = db.deactivate_participant_by_name(100, "@ernest")

    assert removed == {"telegram_user_id": 1, "display_name": "Ernest"}
    assert not db.is_registered(1, chat_id=100)
    assert db.is_registered(1, chat_id=200)
