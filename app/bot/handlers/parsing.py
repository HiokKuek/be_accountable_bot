from __future__ import annotations

import re

_DONE_RE = re.compile(r"^/done(?:@\w+)?\s+([0-3])\s*$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-*•]\s*")
_NUMBERED_MARKER_RE = re.compile(r"^\d+[.)]\s+")


def parse_done_count(text: str) -> int | None:
    match = _DONE_RE.match(text.strip())
    if not match:
        return None
    return int(match.group(1))


def parse_goals(text: str) -> list[str] | None:
    """Parse exactly three bullet goals from /goals or 'checkins:' text."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None

    first = lines[0].lower()
    if not (first.startswith('/goals') or 'checkins' in first):
        return None

    goals: list[str] = []
    for line in lines[1:]:
        cleaned = _BULLET_RE.sub("", line, count=1).strip()
        cleaned = _NUMBERED_MARKER_RE.sub("", cleaned, count=1).strip()
        if cleaned:
            goals.append(cleaned)
    return goals if len(goals) == 3 else None
