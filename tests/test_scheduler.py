from app.handlers.scheduler.daily_jobs import build_scheduler
from tests.conftest import build_env


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_message_sync(self, chat_id: int, text: str) -> int:
        self.sent.append((chat_id, text))
        return 1000 + len(self.sent)


def make_env(tmp_path):
    return build_env(tmp_path / "test.sqlite3")


def mark_registered_before_deadline(env, day, chat_id, *user_ids):
    with env.repositories.schema.connect() as conn:
        for user_id in user_ids:
            conn.execute(
                "UPDATE participants SET registered_at=? WHERE chat_id=? AND telegram_user_id=?",
                (f"{day.isoformat()}T09:00:00+08:00", chat_id, user_id),
            )


def build_test_scheduler(env, telegram):
    return build_scheduler(
        env.reminders,
        env.summaries,
        telegram,
        env.repositories.participants,
        env.repositories.notifications,
    )


def test_scheduler_has_8pm_and_10pm_completion_reminders(tmp_path):
    env = make_env(tmp_path)
    scheduler = build_test_scheduler(env, FakeTelegram())

    job_ids = {job.id for job in scheduler.get_jobs()}

    assert "completion-reminder-20" in job_ids
    assert "completion-reminder-22" in job_ids


def test_completion_reminder_jobs_skip_send_when_everyone_reported(tmp_path):
    env = make_env(tmp_path)
    telegram = FakeTelegram()
    day = env.accountability.today()
    env.repositories.participants.register_user(1, "cyril", "cyril", chat_id=-100)
    env.repositories.participants.register_user(2, "ernest", "Ernest", chat_id=-100)
    env.repositories.checkins.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=-100)
    env.repositories.checkins.upsert_goals(2, day, ["d", "e", "f"], late=False, chat_id=-100)
    env.repositories.checkins.upsert_completion(1, day, 2, chat_id=-100)
    env.repositories.checkins.upsert_completion(2, day, 3, chat_id=-100)
    scheduler = build_test_scheduler(env, telegram)

    scheduler.get_job("completion-reminder-20").func()
    scheduler.get_job("completion-reminder-22").func()

    assert telegram.sent == []


def test_morning_goal_reminder_tags_only_missing_users(tmp_path):
    env = make_env(tmp_path)
    telegram = FakeTelegram()
    day = env.accountability.today()
    env.repositories.participants.register_user(1, "cyril", "cyril", chat_id=-100)
    env.repositories.participants.register_user(2, "ernest", "Ernest", chat_id=-100)
    mark_registered_before_deadline(env, day, -100, 1, 2)
    env.repositories.checkins.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=-100)
    scheduler = build_test_scheduler(env, telegram)

    scheduler.get_job("morning-goal-reminder").func()

    assert len(telegram.sent) == 1
    assert "@ernest" in telegram.sent[0][1]
    assert "@cyril" not in telegram.sent[0][1]
    events = env.repositories.notifications.notification_events_for_day(day, chat_id=-100)
    assert [(event["kind"], event["status"], event["message_id"]) for event in events] == [
        ("morning-goal-reminder", "sent", 1001)
    ]


def test_goal_deadline_summary_sends_when_some_users_are_missing(tmp_path):
    env = make_env(tmp_path)
    telegram = FakeTelegram()
    day = env.accountability.today()
    env.repositories.participants.register_user(1, "cyril", "cyril", chat_id=-100)
    env.repositories.participants.register_user(2, "ernest", "Ernest", chat_id=-100)
    mark_registered_before_deadline(env, day, -100, 1, 2)
    env.repositories.checkins.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=-100)
    scheduler = build_test_scheduler(env, telegram)

    scheduler.get_job("goal-deadline-summary").func()

    assert len(telegram.sent) == 1
    assert "Goal deadline reached" in telegram.sent[0][1]
    assert "@ernest" in telegram.sent[0][1]


def test_scheduler_logs_failed_notification_attempts_and_continues(tmp_path):
    class FailingOnceTelegram(FakeTelegram):
        def send_message_sync(self, chat_id: int, text: str) -> int:
            if chat_id == -100:
                raise RuntimeError("telegram unavailable")
            return super().send_message_sync(chat_id, text)

    env = make_env(tmp_path)
    telegram = FailingOnceTelegram()
    day = env.accountability.today()
    env.repositories.participants.register_user(1, "ernest", "Ernest", chat_id=-100)
    env.repositories.participants.register_user(2, "cyril", "cyril", chat_id=-200)
    mark_registered_before_deadline(env, day, -100, 1)
    mark_registered_before_deadline(env, day, -200, 2)
    scheduler = build_test_scheduler(env, telegram)

    scheduler.get_job("morning-goal-reminder").func()

    assert len(telegram.sent) == 1
    assert telegram.sent[0][0] == -200
    failed = env.repositories.notifications.notification_events_for_day(day, chat_id=-100)
    sent = env.repositories.notifications.notification_events_for_day(day, chat_id=-200)
    assert failed[0]["kind"] == "morning-goal-reminder"
    assert failed[0]["status"] == "failed"
    assert "telegram unavailable" in failed[0]["error"]
    assert sent[0]["status"] == "sent"
