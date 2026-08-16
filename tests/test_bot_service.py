from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.clients.angry import AngryReaction
from app.clients.bible import BibleVerseUnavailable
from app.clients.buddha import BuddhaQuoteUnavailable
from app.repositories.db import Database
from app.services.accountability import AccountabilityService, AnimationReply

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


class FakeBibleVerseClient:
    def __init__(self, verse="Be still.", reference="Psalm 46:10", error=False):
        self.verse = verse
        self.reference = reference
        self.error = error
        self.calls = 0

    def random_verse(self):
        self.calls += 1
        if self.error:
            raise BibleVerseUnavailable("offline")
        return self.verse, self.reference


class FakeBuddhaQuoteClient:
    def __init__(self, quote="Take one careful step.", category="mindfulness", error=False):
        self.quote = quote
        self.category = category
        self.error = error
        self.calls = 0

    def random_quote(self):
        self.calls += 1
        if self.error:
            raise BuddhaQuoteUnavailable("unavailable")
        return self.quote, self.category


class FakeAngryGifClient:
    def __init__(self, caption="Not <done> & annoyed."):
        self.caption = caption
        self.calls = 0

    def random_reaction(self):
        self.calls += 1
        return AngryReaction("https://example.com/angry.gif", self.caption)


def test_angry_returns_escaped_animation_before_registration(tmp_path):
    angry_client = FakeAngryGifClient()
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, angry_gif_client=angry_client)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/angry")

    assert isinstance(response, AnimationReply)
    assert response.animation == "https://example.com/angry.gif"
    assert response.caption is None
    assert angry_client.calls == 1
    assert not service.db.is_registered(1, chat_id=100)


def test_angry_supports_telegram_bot_mention_before_registration(tmp_path):
    angry_client = FakeAngryGifClient()
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, angry_gif_client=angry_client)

    response = service.handle_text(1, None, "Ernest", 100, "/angry@be_accountable_bot")

    assert response.animation == "https://example.com/angry.gif"
    assert angry_client.calls == 1
    assert not service.db.is_registered(1, chat_id=100)


def test_angry_keeps_private_chat_behavior_unchanged(tmp_path):
    angry_client = FakeAngryGifClient()
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, angry_gif_client=angry_client)

    response = service.handle_text(
        1, "ernest", "Ernest", 100, "/angry", chat_type="private"
    )

    assert "can't run in a private chat" in response.lower()
    assert angry_client.calls == 0


def test_amen_returns_escaped_api_verse_without_registration(tmp_path):
    bible_client = FakeBibleVerseClient("Love <God> & others.", "1 John 4:7 & 8")
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, bible_verse_client=bible_client)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/amen")

    assert response == (
        "<b>🙏 Amen</b>\n"
        "<blockquote>Love &lt;God&gt; &amp; others.</blockquote>\n"
        "— <b>1 John 4:7 &amp; 8</b>"
    )
    assert bible_client.calls == 1
    assert not service.db.is_registered(1, chat_id=100)


def test_amen_supports_telegram_bot_mention(tmp_path):
    bible_client = FakeBibleVerseClient()
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, bible_verse_client=bible_client)

    response = service.handle_text(1, None, "Ernest", 100, "/amen@be_accountable_bot")

    assert "Psalm 46:10" in response
    assert bible_client.calls == 1


def test_amen_handles_api_failure_gracefully(tmp_path):
    bible_client = FakeBibleVerseClient(error=True)
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, bible_verse_client=bible_client)

    response = service.handle_text(1, None, "Ernest", 100, "/amen")

    assert "Verse temporarily unavailable" in response


def test_buddha_returns_escaped_original_reflection_without_registration(tmp_path):
    buddha_client = FakeBuddhaQuoteClient("Release <yesterday> & rest.", "letting go")
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, buddha_quote_client=buddha_client)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/buddha")

    assert response == (
        "<b>☸️ Buddha</b>\n"
        "<i>Original reflection · Letting Go</i>\n"
        "<blockquote>Release &lt;yesterday&gt; &amp; rest.</blockquote>"
    )
    assert buddha_client.calls == 1
    assert not service.db.is_registered(1, chat_id=100)


def test_buddha_supports_telegram_bot_mention(tmp_path):
    buddha_client = FakeBuddhaQuoteClient()
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, buddha_quote_client=buddha_client)

    response = service.handle_text(1, None, "Ernest", 100, "/buddha@be_accountable_bot")

    assert "Take one careful step." in response
    assert buddha_client.calls == 1


def test_buddha_handles_local_quote_failure_gracefully(tmp_path):
    buddha_client = FakeBuddhaQuoteClient(error=True)
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, buddha_quote_client=buddha_client)

    response = service.handle_text(1, None, "Ernest", 100, "/buddha")

    assert "Reflection temporarily unavailable" in response


def test_handle_register(tmp_path):
    service = make_service(tmp_path)
    response = service.handle_text(1, "ernest", "Ernest", 100, "/register")
    assert "Registered Ernest" in response


def test_private_chat_commands_get_group_only_intro_and_do_not_register(tmp_path):
    service = make_service(tmp_path)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/register", chat_type="private")

    assert "can't run in a private chat" in response.lower()
    assert "group" in response.lower()
    assert "group" in response.lower()
    assert not service.db.is_registered(1, chat_id=100)
    assert service.db.active_users(chat_id=100) == []


def test_group_registration_allows_more_than_two_players(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")
    service.handle_text(2, "cyril", "cyril", 100, "/register")

    response = service.handle_text(3, "third", "Third", 100, "/register")

    assert "Registered Third" in response
    assert "Participants: 3" in response
    assert service.db.is_registered(3, chat_id=100)


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


def test_done_three_prompts_for_tomorrows_draft(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")

    response = service.handle_text(1, "ernest", "Ernest", 100, "/done 3")

    assert "draft tomorrow's 3 goals" in response
    assert "/goals" in response


def test_goals_after_done_three_draft_tomorrow_and_can_be_overwritten(tmp_path, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 9, 21, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.accountability.datetime", FrozenDateTime)
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    today = date(2026, 7, 9)
    tomorrow = date(2026, 7, 10)
    service.db.upsert_goals(1, today, ["today a", "today b", "today c"], late=False, chat_id=100)
    service.handle_text(1, "ernest", "Ernest", 100, "/done 3")

    response = service.handle_text(1, "ernest", "Ernest", 100, "/goals\n- first a\n- first b\n- first c")
    service.handle_text(1, "ernest", "Ernest", 100, "/goals\n- new a\n- new b\n- new c")

    assert "Goals drafted" in response
    assert "10 Jul 2026" in response
    assert service.db.get_checkin(1, today, chat_id=100)["goals"] == ["today a", "today b", "today c"]
    assert service.db.get_checkin(1, tomorrow, chat_id=100) is None
    assert service.db.get_goal_draft(1, tomorrow, chat_id=100)["goals"] == ["new a", "new b", "new c"]


def test_confirmgoals_promotes_todays_draft(tmp_path, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 10, 8, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.accountability.datetime", FrozenDateTime)
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    day = date(2026, 7, 10)
    service.db.upsert_goal_draft(1, day, ["draft a", "draft b", "draft c"], chat_id=100)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/confirmgoals")

    assert "Draft confirmed" in response
    assert service.db.get_checkin(1, day, chat_id=100)["goals"] == ["draft a", "draft b", "draft c"]
    assert service.db.get_goal_draft(1, day, chat_id=100) is None


def test_fresh_goals_on_drafted_day_are_official_and_supersede_draft(tmp_path, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 10, 8, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.accountability.datetime", FrozenDateTime)
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    day = date(2026, 7, 10)
    service.db.upsert_goal_draft(1, day, ["draft a", "draft b", "draft c"], chat_id=100)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/goals\n- fresh a\n- fresh b\n- fresh c")

    assert "Goals recorded" in response
    assert service.db.get_checkin(1, day, chat_id=100)["goals"] == ["fresh a", "fresh b", "fresh c"]
    assert service.db.get_goal_draft(1, day, chat_id=100) is None


def test_confirmgoals_without_todays_draft_explains_how_to_submit(tmp_path):
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/confirmgoals")

    assert "No draft to confirm" in response
    assert "/goals" in response


def test_today_summary_shows_logged_goals_as_pending_before_completion_cutoff(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, "ernest", "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["gym", "study", "sleep early"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["work", "run", "read"], late=False, chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 9, 22, 0, tzinfo=SGT))

    assert "<b>👤 cyril</b>" in response
    assert "1. gym" in response
    assert "2. study" in response
    assert "3. sleep early" in response
    assert "<b>👤 Ernest</b>" in response
    assert "1. work" in response
    assert "2. run" in response
    assert "3. read" in response
    assert "Status: <b>⏳ Pending</b>" in response
    assert "Progress: <code>not reported</code>" in response
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

    assert "<b>👤 cyril</b>\nStatus:" in response
    assert "\n\n<b>👤 Ernest</b>\nStatus:" in response
    assert "\n<b>Goals</b>\n" in response


def test_today_summary_marks_missing_goals_failed_after_10am(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 9, 10, 1, tzinfo=SGT))

    assert "Status: <b>❌ Fail</b>" in response
    assert "Progress: <code>no goals logged</code>" in response


def test_after_deadline_registration_grace_accepts_same_day_goals_without_late_fail(tmp_path, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 9, 10, 30, tzinfo=tz)

    monkeypatch.setattr("app.services.accountability.datetime", FrozenDateTime)
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "late", "Late Joiner", chat_id=100)
    with service.db.connect() as conn:
        conn.execute(
            "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
            ("2026-07-09T10:30:00+08:00", 100, 1),
        )

    response = service.handle_text(1, "late", "Late Joiner", 100, """/goals
- a
- b
- c""")
    row = service.db.get_checkin(1, day, chat_id=100)

    assert "Late:" not in response
    assert row["goals_status"] == "submitted"
    assert "Status: <b>⏳ Pending</b>" in service.today_summary(day, chat_id=100, now=FrozenDateTime.now(SGT))


def test_after_deadline_goals_edit_preserves_on_time_status_in_today_and_score(tmp_path, monkeypatch):
    class MutableDateTime(datetime):
        current_hour = 9

        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 9, cls.current_hour, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.accountability.datetime", MutableDateTime)
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    day = date(2026, 7, 9)

    service.handle_text(1, "ernest", "Ernest", 100, "/goals\n- first a\n- first b\n- first c")
    MutableDateTime.current_hour = 11
    response = service.handle_text(1, "ernest", "Ernest", 100, "/goals\n- edited a\n- edited b\n- edited c")
    service.handle_text(1, "ernest", "Ernest", 100, "/done 2")

    row = service.db.get_checkin(1, day, chat_id=100)
    today = service.today_summary(day, chat_id=100, now=MutableDateTime.now(SGT))
    score = service.month_score(chat_id=100, year=2026, month=7)

    assert "Late:" not in response
    assert row["goals"] == ["edited a", "edited b", "edited c"]
    assert row["goals_status"] == "submitted"
    assert "Status: <b>✅ Pass</b>" in today
    assert "Ernest — <b>0</b> failed days" in score


def test_first_goals_submission_after_deadline_is_still_late(tmp_path, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 9, 11, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.accountability.datetime", FrozenDateTime)
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    with service.db.connect() as conn:
        conn.execute(
            "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
            ("2026-07-09T08:00:00+08:00", 100, 1),
        )

    response = service.handle_text(1, "ernest", "Ernest", 100, "/goals\n- a\n- b\n- c")
    row = service.db.get_checkin(1, date(2026, 7, 9), chat_id=100)

    assert "Late:" in response
    assert row["goals_status"] == "late_submitted"
    assert "Status: <b>❌ Fail</b>" in service.today_summary(
        date(2026, 7, 9), chat_id=100, now=FrozenDateTime.now(SGT)
    )


def test_today_summary_marks_missing_completion_failed_after_5am_next_day(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.upsert_goals(1, day, ["gym", "study", "sleep early"], late=False, chat_id=100)

    response = service.today_summary(day, chat_id=100, now=datetime(2026, 7, 10, 5, 1, tzinfo=SGT))

    assert "<b>👤 cyril</b>" in response
    assert "Status: <b>❌ Fail</b>" in response
    assert "Progress: <code>not reported</code>" in response


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


def test_goal_reminders_distinguish_drafts_from_users_with_no_goals(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 9)
    service.db.register_user(1, "drafted", "Drafted", chat_id=100)
    service.db.register_user(2, "missing", "Missing", chat_id=100)
    service.db.upsert_goal_draft(1, day, ["a", "b", "c"], chat_id=100)

    morning = service.morning_reminder(chat_id=100, checkin_date=day)
    final = service.missing_goals_reminder(chat_id=100, checkin_date=day)

    for response in (morning, final):
        assert "Draft ready — confirm or replace" in response
        assert "@drafted" in response
        assert "/confirmgoals" in response
        assert "Still missing goals" in response
        assert "@missing" in response


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

    assert "All goals are keyed" in response
    assert "<b>👤 cyril</b>" in response
    assert "1. settle sep coursereg" in response
    assert "<b>👤 Ernest</b>" in response
    assert "1. x leetcode" in response
    assert "<b>💬 QOTD</b>" in response
    assert "<blockquote><i>Consistency beats intensity</i></blockquote>" in response
    assert "— Internet Quote API" in response
    assert "\n\n<b>👤 Ernest</b>" in response
    assert qotd_client.calls == 1


def test_qotd_escapes_api_response_html(tmp_path):
    qotd_client = FakeQotdClient("<ship> daily", "A&B")
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    service = AccountabilityService(db, qotd_client=qotd_client)

    response = service.qotd()

    assert "&lt;ship&gt; daily" in response
    assert "A&amp;B" in response


def test_score_uses_multi_user_leaderboard_not_net_settlement(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 1)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    service.db.register_user(2, "friend", "Friend", chat_id=100)
    service.db.register_user(3, "third", "Third", chat_id=100)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(1, day, 3, chat_id=100)
    service.db.upsert_goals(2, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(2, day, 1, chat_id=100)
    service.db.upsert_goals(3, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_completion(3, day, 0, chat_id=100)

    response = service.month_score(chat_id=100, year=2026, month=7)

    assert "Leaderboard" in response
    assert "1. Ernest — <b>0</b> failed days — <b>$0</b>" in response
    assert "2. Friend — <b>1</b> failed day — <b>$5</b>" in response
    assert "3. Third — <b>1</b> failed day — <b>$5</b>" in response
    assert "pays" not in response
    assert "Group total: <b>$10</b>" in response


def test_remove_deactivates_participant_only_for_current_group(tmp_path):
    service = make_service(tmp_path)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    service.db.register_user(2, "friend", "Friend", chat_id=100)
    service.db.register_user(2, "friend", "Friend", chat_id=200)

    response = service.handle_text(1, "ernest", "Ernest", 100, "/remove @friend")

    assert "Removed Friend" in response
    assert not service.db.is_registered(2, chat_id=100)
    assert service.db.is_registered(2, chat_id=200)


def test_deadline_summary_posts_submitted_goals_and_tags_missing_users(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 1)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    service.db.register_user(2, "friend", "Friend", chat_id=100)
    service.db.register_user(3, "third", "Third", chat_id=100)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["d", "e", "f"], late=False, chat_id=100)

    response = service.goal_deadline_summary(day, chat_id=100)

    assert "Goal deadline reached" in response
    assert "Submitted: <b>2/3</b>" in response
    assert "@third" in response
    assert "Ernest" in response
    assert "Friend" in response


def test_deadline_summary_skips_when_all_users_already_submitted(tmp_path):
    service = make_service(tmp_path)
    day = date(2026, 7, 1)
    service.db.register_user(1, "ernest", "Ernest", chat_id=100)
    service.db.register_user(2, "friend", "Friend", chat_id=100)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["d", "e", "f"], late=False, chat_id=100)

    assert service.goal_deadline_summary(day, chat_id=100) is None


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
    assert "Ernest" in score
    assert "Friend" in score
    assert "pays" not in score
    assert "Outsider" not in score
