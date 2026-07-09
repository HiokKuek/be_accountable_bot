from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.db import Database
from app.service import AccountabilityService

SGT = ZoneInfo("Asia/Singapore")


def make_service(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    return AccountabilityService(db)


def test_handle_register(tmp_path):
    service = make_service(tmp_path)
    response = service.handle_text(1, "ernest", "Ernest", 100, "/register")
    assert "Registered Ernest" in response


def test_handle_goals_requires_registration(tmp_path):
    service = make_service(tmp_path)
    response = service.handle_text(1, "ernest", "Ernest", 100, """/goals
- a
- b
- c""")
    assert "register first" in response.lower()


def test_handle_goals_and_done(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")
    response = service.handle_text(1, "ernest", "Ernest", 100, """/goals
- investment
- intervals
- read""")
    assert "goals recorded" in response.lower()
    response = service.handle_text(1, "ernest", "Ernest", 100, "/done 2")
    assert "2/3" in response
    assert "Pass" in response


def test_today_summary_shows_logged_goals_as_pending_before_completion_cutoff(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, "ernest", "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["gym", "study", "sleep early"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["work", "run", "read"], late=False, chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 9, 22, 0, tzinfo=SGT))

    assert "cyril" in response
    assert "1. gym" in response
    assert "2. study" in response
    assert "3. sleep early" in response
    assert "Ernest" in response
    assert "1. work" in response
    assert "2. run" in response
    assert "3. read" in response
    assert "not reported — ⏳ pending" in response
    assert "❌ fail" not in response


def test_today_summary_marks_missing_goals_failed_after_10am(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 9, 10, 1, tzinfo=SGT))

    assert "cyril: no goals logged — ❌ fail" in response


def test_today_summary_marks_missing_completion_failed_after_5am_next_day(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.upsert_goals(1, day, ["gym", "study", "sleep early"], late=False, chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 10, 5, 1, tzinfo=SGT))

    assert "cyril" in response
    assert "not reported — ❌ fail" in response


def test_score_uses_net_settlement(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")
    service.handle_text(2, "friend", "Friend", 100, "/register")
    service.db.upsert_goals(1, date(2026, 7, 1), ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(1, date(2026, 7, 1), 1, chat_id=100)
    service.db.upsert_goals(2, date(2026, 7, 1), ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(2, date(2026, 7, 1), 3, chat_id=100)
    response = service.handle_text(1, "ernest", "Ernest", 100, "/score")
    assert "Ernest pays Friend $5" in response


def test_registration_roster_is_scoped_to_group(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")
    service.handle_text(2, "outsider", "Outsider", 200, "/register")

    response = service.handle_text(3, "friend", "Friend", 100, "/register")

    assert "Ernest" in response
    assert "Friend" in response
    assert "Outsider" not in response


def test_user_registered_in_one_group_is_not_registered_in_another(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")

    response = service.handle_text(1, "ernest", "Ernest", 200, "/done 2")

    assert "register first" in response.lower()


def test_today_and_score_are_scoped_to_group(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 1)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    service.db.register_user(2, "friend", "Friend", chat_id=100)
    service.db.register_user(3, "outsider", "Outsider", chat_id=200)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(1, day, 1, chat_id=100)
    service.db.upsert_goals(2, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(2, day, 3, chat_id=100)
    service.db.upsert_goals(3, day, ["x", "y", "z"], late=False, chat_id=200)
    service.db.upsert_completion(3, day, 0, chat_id=200)

    today = service.today_summary(day, chat_id=100)
    score = service.month_score(chat_id=100, year=2026, month=7)

    assert "Ernest" in today
    assert "Friend" in today
    assert "Outsider" not in today
    assert "Ernest pays Friend $5" in score
    assert "Outsider" not in score
