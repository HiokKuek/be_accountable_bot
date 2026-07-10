import httpx
import pytest

from app.qotd import DEFAULT_QOTD_API_URL, QotdApiClient, QotdUnavailable


def test_default_qotd_api_url_uses_daily_quote_endpoint():
    assert DEFAULT_QOTD_API_URL == "https://zenquotes.io/api/today"


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
