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


def monthly_leaderboard(failed_days_by_user: dict[str, int], penalty_amount: int) -> list[dict[str, object]]:
    """Rank participants by fewest failed days and compute each user's penalty total."""
    ranked = sorted(failed_days_by_user.items(), key=lambda item: (item[1], item[0].casefold()))
    return [
        {
            "rank": rank,
            "name": name,
            "failed_days": failed_days,
            "penalty": failed_days * penalty_amount,
        }
        for rank, (name, failed_days) in enumerate(ranked, start=1)
    ]
