from datetime import date

from app.db import Database
from app.service import AccountabilityService


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


def test_score_uses_net_settlement(tmp_path):
    service = make_service(tmp_path)
    service.handle_text(1, "ernest", "Ernest", 100, "/register")
    service.handle_text(2, "friend", "Friend", 100, "/register")
    service.db.upsert_goals(1, date(2026, 7, 1), ["a", "b", "c"], late=False)
    service.db.upsert_completion(1, date(2026, 7, 1), 1)
    service.db.upsert_goals(2, date(2026, 7, 1), ["a", "b", "c"], late=False)
    service.db.upsert_completion(2, date(2026, 7, 1), 3)
    response = service.handle_text(1, "ernest", "Ernest", 100, "/score")
    assert "Ernest pays Friend $5" in response
