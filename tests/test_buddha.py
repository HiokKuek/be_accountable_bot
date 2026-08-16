from app.clients.buddha import LocalBuddhaQuoteClient, ORIGINAL_REFLECTIONS


def test_reflection_bank_has_five_populated_categories():
    assert set(ORIGINAL_REFLECTIONS) == {
        "mindfulness",
        "impermanence",
        "compassion",
        "discipline",
        "letting go",
    }
    assert all(len(quotes) >= 3 for quotes in ORIGINAL_REFLECTIONS.values())
    assert all(quote.strip() for quotes in ORIGINAL_REFLECTIONS.values() for quote in quotes)


def test_local_client_returns_a_reflection_and_its_category():
    quote, category = LocalBuddhaQuoteClient().random_quote()

    assert category in ORIGINAL_REFLECTIONS
    assert quote in ORIGINAL_REFLECTIONS[category]
