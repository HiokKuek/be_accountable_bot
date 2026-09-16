from __future__ import annotations


def assess_day_result(*, goals_submitted: bool, completed_count: int | None) -> str:
    if not goals_submitted:
        return "fail"
    if completed_count is None:
        return "fail"
    return "pass" if completed_count >= 2 else "fail"


def monthly_leaderboard(failed_days_by_user: dict[str, int], penalty_amount: int) -> list[dict[str, object]]:
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
