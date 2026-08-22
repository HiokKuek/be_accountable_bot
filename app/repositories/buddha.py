from __future__ import annotations

import random
from typing import Protocol


ORIGINAL_REFLECTIONS: dict[str, tuple[str, ...]] = {
    "mindfulness": (
        "Return to this breath; it is the only task asking for you now.",
        "Notice the hurry, then give the next moment your full attention.",
        "A quiet mind begins by listening without reaching.",
        "Let each small action know it is being done.",
    ),
    "impermanence": (
        "What changes is not betraying you; it is showing its nature.",
        "Meet this season fully, knowing it will not keep its shape.",
        "The passing moment asks to be cherished, not captured.",
        "When conditions change, wisdom changes its grip.",
    ),
    "compassion": (
        "Make room for another person's struggle without abandoning your own.",
        "Kindness can be firm and still leave no wound behind.",
        "Before judging the path, remember how heavy an unseen burden can be.",
        "Offer patience where you once needed it yourself.",
    ),
    "discipline": (
        "A steady practice is built from promises small enough to keep today.",
        "Begin again without drama; the path also includes returning.",
        "Let your habits carry you when enthusiasm grows quiet.",
        "Choose the useful step, especially when no one is watching.",
    ),
    "letting go": (
        "Release the argument you keep rehearsing with yesterday.",
        "Set down what cannot be carried into the next honest step.",
        "Letting go is making space, not erasing what mattered.",
        "You can loosen your hold before you know what comes next.",
    ),
}


class BuddhaQuoteUnavailable(RuntimeError):
    pass


class BuddhaQuoteClient(Protocol):
    def random_quote(self) -> tuple[str, str]:
        ...


class LocalBuddhaQuoteClient:
    def random_quote(self) -> tuple[str, str]:
        choices = [
            (quote, category)
            for category, quotes in ORIGINAL_REFLECTIONS.items()
            for quote in quotes
            if quote.strip()
        ]
        if not choices:
            raise BuddhaQuoteUnavailable("Local reflection bank is empty")
        return random.choice(choices)
