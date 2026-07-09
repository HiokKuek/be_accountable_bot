from app.db import Database
from app.scheduler import build_scheduler
from app.service import AccountabilityService


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_message_sync(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def make_service(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    return AccountabilityService(db)


def test_scheduler_has_8pm_and_10pm_completion_reminders(tmp_path):
    service = make_service(tmp_path)
    scheduler = build_scheduler(service, FakeTelegram())

    job_ids = {job.id for job in scheduler.get_jobs()}

    assert "completion-reminder-20" in job_ids
    assert "completion-reminder-22" in job_ids


def test_completion_reminder_jobs_skip_send_when_everyone_reported(tmp_path):
    service = make_service(tmp_path)
    telegram = FakeTelegram()
    day = service.today()
    service.db.register_user(1, "cyril", "cyril", chat_id=100)
    service.db.register_user(2, "ernest", "Ernest", chat_id=100)
    service.db.upsert_goals(1, day, ["a", "b", "c"], late=False, chat_id=100)
    service.db.upsert_goals(2, day, ["d", "e", "f"], late=False, chat_id=100)
    service.db.upsert_completion(1, day, 2, chat_id=100)
    service.db.upsert_completion(2, day, 3, chat_id=100)
    scheduler = build_scheduler(service, telegram)

    scheduler.get_job("completion-reminder-20").func()
    scheduler.get_job("completion-reminder-22").func()

    assert telegram.sent == []
