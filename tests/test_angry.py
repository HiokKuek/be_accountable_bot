from app.angry import (
    LOCAL_ANGRY_REACTIONS,
    TENOR_SEARCH_URL,
    AngryGifClient,
    AngryReaction,
)
from app.settings import Settings


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def get(self, url, params):
        self.requests.append((url, params))
        return self.response


class FakeFallback:
    def __init__(self):
        self.reaction = AngryReaction("https://fallback.example/angry.gif", "Fallback rage")
        self.calls = 0

    def random_reaction(self):
        self.calls += 1
        return self.reaction


def test_tenor_is_preferred_when_api_key_is_configured():
    http_client = FakeHttpClient(
        FakeResponse(
            {
                "results": [
                    {
                        "media_formats": {
                            "gif": {"url": "https://media.tenor.com/angry.gif"}
                        }
                    }
                ]
            }
        )
    )
    fallback = FakeFallback()
    client = AngryGifClient(
        tenor_api_key="secret", http_client=http_client, fallback=fallback
    )

    reaction = client.random_reaction()

    assert reaction.url == "https://media.tenor.com/angry.gif"
    assert fallback.calls == 0
    assert http_client.requests == [
        (
            TENOR_SEARCH_URL,
            {
                "q": "angry reaction",
                "key": "secret",
                "client_key": "accountability_bot",
                "limit": 10,
                "media_filter": "gif",
                "contentfilter": "high",
                "random": "true",
            },
        )
    ]


def test_missing_tenor_key_uses_local_fallback_without_api_call():
    http_client = FakeHttpClient(FakeResponse({}))
    fallback = FakeFallback()
    client = AngryGifClient(http_client=http_client, fallback=fallback)

    assert client.random_reaction() == fallback.reaction
    assert fallback.calls == 1
    assert http_client.requests == []


def test_tenor_failure_uses_local_fallback():
    fallback = FakeFallback()
    client = AngryGifClient(
        tenor_api_key="secret",
        http_client=FakeHttpClient(FakeResponse(error=RuntimeError("offline"))),
        fallback=fallback,
    )

    assert client.random_reaction() == fallback.reaction
    assert fallback.calls == 1


def test_curated_fallback_bank_contains_usable_gifs_and_captions():
    assert len(LOCAL_ANGRY_REACTIONS) >= 3
    assert all(item.url.startswith("https://") for item in LOCAL_ANGRY_REACTIONS)
    assert all(item.url.endswith(".gif") for item in LOCAL_ANGRY_REACTIONS)
    assert all(item.caption.strip() for item in LOCAL_ANGRY_REACTIONS)


def test_tenor_api_key_is_loaded_from_settings(monkeypatch):
    monkeypatch.setenv("TENOR_API_KEY", "configured-key")

    assert Settings(_env_file=None).tenor_api_key == "configured-key"
