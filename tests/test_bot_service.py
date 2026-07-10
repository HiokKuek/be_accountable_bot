from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.db import Database
from app.service import AccountabilityService

SGT = ZoneInfo("Asia/Singapore")


def make_service(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    return AccountabilityService(db)


class FakeQotdClient:
    def __init__(self, quote="API discipline quote", author="API Author"):
        self.quote = quote
        self.author = author
        self.calls = 0

    def quote_of_the_day(self):
        self.calls += 1
        return self.quote, self.author


def test_handle_register(tmp_path):
    service = make_service(tmp_path)
    response = service.handle_text(1, "ernest", "Ernest", 100, "/register")
    assert "Registered Ernest" in response


def test_private_chat_commands_get_group_only_intro_and_do_not_register(tmp_path):
    service = make_service(tmp_path)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/register", chat_type="private")

    assert "can't run in a private chat" in response.lower()
    assert "group" in response.lower()
    assert "2 people" in response
    assert not service.db.is_registered(1, chat_id=100)
    assert service.db.active_users(chat_id=100) == []


def test_group_registration_is_limited_to_two_players(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")
    service.handle_text(2, "cyril", "cyril", 100, "/register")

    response = service.handle_text(3, "third", "Third", 100, "/register")

    assert "already has 2 players" in response
    assert not service.db.is_registered(3, chat_id=100)


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

    assert "<b>cyril</b>" in response
    assert "1. gym" in response
    assert "2. study" in response
    assert "3. sleep early" in response
    assert "<b>Ernest</b>" in response
    assert "1. work" in response
    assert "2. run" in response
    assert "3. read" in response
    assert "Status: ⏳ pending — not reported" in response
    assert "<b>pending</b>" not in response
    assert "❌ fail" not in response


def test_today_summary_separates_players_with_blank_line_and_bolds_names(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, "ernest", "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["settle sep coursereg", "chest and back", "read"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["x leetcode", "gym", "read"], late=False, chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 9, 22, 0, tzinfo=SGT))

    assert "<b>cyril</b>\nStatus:" in response
    assert "\n\n<b>Ernest</b>\nStatus:" in response
    assert "\nGoals\n" in response
    assert "<b>Goals</b>" not in response


def test_today_summary_marks_missing_goals_failed_after_10am(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 9, 10, 1, tzinfo=SGT))

    assert "Status: ❌ fail — no goals logged" in response


def test_today_summary_marks_missing_completion_failed_after_5am_next_day(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.upsert_goals(1, day, ["gym", "study", "sleep early"], late=False, chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 10, 5, 1, tzinfo=SGT))

    assert "<b>cyril</b>" in response
    assert "Status: ❌ fail — not reported" in response


def test_reminders_return_none_when_everyone_has_done_the_required_action(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, "ernest", "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["d", "e", "f"], late=False, chat_id=100)
    service.db.upsert_completion(1, day, 2, chat_id=100)
    service.db.upsert_completion(2, day, 3, chat_id=100)

    assert service.missing_goals_reminder(chat_id=100, checkin_date=day) is None
    assert service.completion_reminder(chat_id=100, checkin_date=day) is None


def test_reminders_tag_only_missing_users(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, None, "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)

    goal_reminder = service.missing_goals_reminder(chat_id=100, checkin_date=day)
    done_reminder = service.completion_reminder(chat_id=100, checkin_date=day)

    assert '<a href="tg://user?id=2">Ernest</a>' in goal_reminder
    assert "@cyril" not in goal_reminder
    assert "@cyril" in done_reminder
    assert '<a href="tg://user?id=2">Ernest</a>' in done_reminder


def test_goal_confirmation_summary_thanks_users_shows_goals_and_api_qotd(tmp_path):
    qotd_client = FakeQotdClient("Consistency beats intensity", "Internet Quote API")
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, qotd_client=qotd_client)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, "ernest", "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["settle sep coursereg", "chest and back", "read"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["x leetcode", "gym", "read"], late=False, chat_id=100)

    response = service.goal_confirmation_summary(day, chat_id=100)

    assert "Great thanks for keying your goals" in response
    assert "<b>cyril</b>" in response
    assert "1. settle sep coursereg" in response
    assert "<b>Ernest</b>" in response
    assert "1. x leetcode" in response
    assert "<b>QOTD</b>" in response
    assert "<i>Consistency beats intensity</i>" in response
    assert "— Internet Quote API" in response
    assert "\n\n<b>Ernest</b>" in response
    assert qotd_client.calls == 1


def test_qotd_escapes_api_response_html(tmp_path):
    qotd_client = FakeQotdClient("<ship> daily", "A&B")
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, qotd_client=qotd_client)

    response = service.qotd()

    assert "&lt;ship&gt; daily" in response
    assert "A&amp;B" in response


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
