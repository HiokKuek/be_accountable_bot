import httpx
import pytest

from app.core.settings import Settings
from app.clients.bible import DEFAULT_BIBLE_VERSE_API_URL, BibleVerseApiClient, BibleVerseUnavailable


def test_default_bible_verse_api_url_uses_random_verse_endpoint():
    assert DEFAULT_BIBLE_VERSE_API_URL == "https://bible-api.com/?random=verse"


def test_settings_default_bible_verse_api_url_matches_random_verse_endpoint():
    settings = Settings(_env_file=None)

    assert settings.bible_verse_api_url == DEFAULT_BIBLE_VERSE_API_URL


def test_bible_verse_api_client_parses_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/random"
        return httpx.Response(200, json={"text": "  Be still.\n", "reference": " Psalm 46:10 "})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = BibleVerseApiClient(api_url="https://example.test/random", http_client=http_client)

    assert client.random_verse() == ("Be still.", "Psalm 46:10")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"text": "", "reference": "Psalm 46:10"},
        {"text": "Be still.", "reference": ""},
    ],
)
def test_bible_verse_api_client_rejects_malformed_payload(payload):
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    client = BibleVerseApiClient(api_url="https://example.test/random", http_client=http_client)

    with pytest.raises(BibleVerseUnavailable):
        client.random_verse()


def test_bible_verse_api_client_wraps_request_failures():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = BibleVerseApiClient(api_url="https://example.test/random", http_client=http_client)

    with pytest.raises(BibleVerseUnavailable):
        client.random_verse()
