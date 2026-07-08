from datetime import date

from app.domain import assess_day_result, net_settlement


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


def test_net_settlement_tie_means_no_payment():
    result = net_settlement({"ernest": 2, "friend": 2}, penalty_amount=5)
    assert result == {"payer": None, "receiver": None, "amount": 0, "difference": 0}


def test_net_settlement_worse_performer_pays_difference():
    result = net_settlement({"ernest": 5, "friend": 2}, penalty_amount=5)
    assert result == {"payer": "ernest", "receiver": "friend", "amount": 15, "difference": 3}
