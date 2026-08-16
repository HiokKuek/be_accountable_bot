from datetime import date

import httpx
import pytest

from app.core.settings import Settings
from app.clients.qotd import DEFAULT_QOTD_API_URL, QotdApiClient, QotdUnavailable


def test_default_qotd_api_url_uses_daily_quote_endpoint():
    assert DEFAULT_QOTD_API_URL == "https://zenquotes.io/api/today"


def test_settings_default_qotd_api_url_matches_daily_quote_endpoint():
    settings = Settings(_env_file=None)

    assert settings.qotd_api_url == DEFAULT_QOTD_API_URL


def test_qotd_api_client_parses_zenquotes_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/random"
        return httpx.Response(200, json=[{"q": "Build daily.", "a": "Test Author"}])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = QotdApiClient(api_url="https://example.test/random", http_client=http_client)

    assert client.quote_of_the_day() == ("Build daily.", "Test Author")


def test_qotd_api_client_rejects_empty_quote_response():
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    client = QotdApiClient(api_url="https://example.test/random", http_client=http_client)

    with pytest.raises(QotdUnavailable):
        client.quote_of_the_day()


def test_qotd_api_client_returns_cached_quote_for_same_day_when_subsequent_calls_would_rate_limit():
    calls = 0
    current_day = {"value": date(2026, 8, 5)}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=[{"q": "Build daily.", "a": "Test Author"}])
        return httpx.Response(429, json={"error": "Too many requests"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = QotdApiClient(
        api_url="https://example.test/today",
        http_client=http_client,
        today_provider=lambda: current_day["value"],
    )

    assert client.quote_of_the_day() == ("Build daily.", "Test Author")
    assert client.quote_of_the_day() == ("Build daily.", "Test Author")
    assert calls == 1


def test_qotd_api_client_refreshes_cache_on_new_day():
    calls = 0
    current_day = {"value": date(2026, 8, 5)}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=[{"q": "Build daily.", "a": "Test Author"}])
        return httpx.Response(200, json=[{"q": "Ship daily.", "a": "Second Author"}])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = QotdApiClient(
        api_url="https://example.test/today",
        http_client=http_client,
        today_provider=lambda: current_day["value"],
    )

    assert client.quote_of_the_day() == ("Build daily.", "Test Author")
    current_day["value"] = date(2026, 8, 6)
    assert client.quote_of_the_day() == ("Ship daily.", "Second Author")
    assert calls == 2
