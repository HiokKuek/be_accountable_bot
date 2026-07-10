import httpx
import pytest

from app.qotd import QotdApiClient, QotdUnavailable


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
