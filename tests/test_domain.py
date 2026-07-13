from datetime import date

from app.domain import assess_day_result, monthly_leaderboard


def test_done_two_or_three_passes():
    assert assess_day_result(goals_submitted=True, completed_count=2) == "pass"
    assert assess_day_result(goals_submitted=True, completed_count=3) == "pass"


def test_done_zero_or_one_fails():
    assert assess_day_result(goals_submitted=True, completed_count=0) == "fail"
    assert assess_day_result(goals_submitted=True, completed_count=1) == "fail"


def test_missing_goals_fails_even_if_completion_count_exists():
    assert assess_day_result(goals_submitted=False, completed_count=3) == "fail"


def test_missing_completion_fails():
    assert assess_day_result(goals_submitted=True, completed_count=None) == "fail"


def test_monthly_leaderboard_ranks_fewer_failures_first_with_penalties():
    result = monthly_leaderboard({"ernest": 1, "friend": 3, "third": 0}, penalty_amount=5)

    assert result == [
        {"rank": 1, "name": "third", "failed_days": 0, "penalty": 0},
        {"rank": 2, "name": "ernest", "failed_days": 1, "penalty": 5},
        {"rank": 3, "name": "friend", "failed_days": 3, "penalty": 15},
    ]
