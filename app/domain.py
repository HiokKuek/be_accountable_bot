from __future__ import annotations


def assess_day_result(*, goals_submitted: bool, completed_count: int | None) -> str:
    """Return pass/fail for one user's day.

    Rules:
    - Missing goals fail the day.
    - Missing completion report fails the day.
    - 2/3 or 3/3 completed passes.
    - 0/3 or 1/3 completed fails.
    """
    if not goals_submitted:
        return "fail"
    if completed_count is None:
        return "fail"
    return "pass" if completed_count >= 2 else "fail"


def net_settlement(failed_days_by_user: dict[str, int], penalty_amount: int) -> dict[str, object]:
    """Compute net monthly settlement for two users.

    The user with more failed days pays the other penalty_amount × difference.
    If tied, nobody pays.
    """
    if len(failed_days_by_user) < 2:
        return {"payer": None, "receiver": None, "amount": 0, "difference": 0}
    ranked = sorted(failed_days_by_user.items(), key=lambda item: item[1], reverse=True)
    payer, payer_failures = ranked[0]
    receiver, receiver_failures = ranked[1]
    difference = payer_failures - receiver_failures
    if difference <= 0:
        return {"payer": None, "receiver": None, "amount": 0, "difference": 0}
    return {
        "payer": payer,
        "receiver": receiver,
        "amount": difference * penalty_amount,
        "difference": difference,
    }
