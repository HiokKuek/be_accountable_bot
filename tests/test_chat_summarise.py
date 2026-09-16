import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.domain.models import MessageContext
from app.repositories.openrouter import OpenRouterClient
from app.services.chat_summarise import ChatMessageBuffer, ChatSummariseService

SGT = ZoneInfo("Asia/Singapore")


class FakeResponse:
    def __init__(self, payload, *, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

    def raise_for_status(self):
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request, json=self._payload)
            raise httpx.HTTPStatusError("OpenRouter error", request=self.request, response=response)

    def json(self):
        return self._payload


class FakeAsyncHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def post(self, url, *, headers, json):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return self.responses.pop(0)


def make_context(chat_id=100):
    return MessageContext(
        user_id=1,
        username="ernest",
        display_name="Ernest",
        chat_id=chat_id,
        chat_title="Focus Group",
        chat_type="group",
    )


def test_chat_message_buffer_keeps_only_latest_messages():
    buffer = ChatMessageBuffer(per_chat_limit=2)
    context = make_context()

    buffer.record(context, "first", now=datetime(2026, 9, 16, 9, 0, tzinfo=SGT))
    buffer.record(context, "second", now=datetime(2026, 9, 16, 9, 1, tzinfo=SGT))
    buffer.record(context, "third", now=datetime(2026, 9, 16, 9, 2, tzinfo=SGT))

    assert [message.text for message in buffer.recent_messages(100)] == ["second", "third"]


def test_summarise_reports_missing_cache_before_calling_openrouter():
    service = ChatSummariseService(OpenRouterClient(api_key="", model=""), ChatMessageBuffer())

    response = asyncio.run(service.summarise(make_context()))

    assert "Chat summary unavailable" in response
    assert "don't have any recent messages cached" in response


def test_summarise_returns_configuration_hint_when_key_is_missing():
    buffer = ChatMessageBuffer()
    context = make_context()
    buffer.record(context, "hello team")
    service = ChatSummariseService(OpenRouterClient(api_key="", model="google/gemma-4-31b-it:free"), buffer)

    response = asyncio.run(service.summarise(context))

    assert "/summarise is not configured" in response
    assert "OPENROUTER_API_KEY" in response


def test_summarise_formats_and_escapes_openrouter_output():
    fake_http = FakeAsyncHttpClient(
        [FakeResponse({"choices": [{"message": {"content": "TL;DR:\n- <done> & celebrated"}}]})]
    )
    client = OpenRouterClient(api_key="secret", model="google/gemma-4-31b-it:free", http_client=fake_http)
    buffer = ChatMessageBuffer()
    context = make_context()
    buffer.record(context, "We finished the task", now=datetime(2026, 9, 16, 9, 0, tzinfo=SGT))
    service = ChatSummariseService(client, buffer)

    response = asyncio.run(service.summarise(context))

    assert "Chat Summary" in response
    assert "last 1 captured messages" in response
    assert "&lt;done&gt; &amp; celebrated" in response
    assert fake_http.requests[0]["json"]["model"] == "google/gemma-4-31b-it:free"
    assert "We finished the task" in fake_http.requests[0]["json"]["messages"][1]["content"]


def test_openrouter_client_falls_back_to_secondary_model_after_failure():
    fake_http = FakeAsyncHttpClient(
        [
            FakeResponse({"error": {"message": "rate limited"}}, status_code=429),
            FakeResponse({"error": {"message": "provider returned error"}}, status_code=429),
            FakeResponse({"choices": [{"message": {"content": "Fallback summary"}}]}),
        ]
    )
    client = OpenRouterClient(
        api_key="secret",
        model="google/gemma-4-31b-it:free",
        fallback_model="google/gemma-4-26b-a4b-it:free",
        http_client=fake_http,
    )

    summary = asyncio.run(client.summarize_messages("Summarise this chat"))

    assert summary == "Fallback summary"
    assert [request["json"]["model"] for request in fake_http.requests] == [
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "openrouter/free",
    ]


def test_openrouter_client_normalizes_legacy_gemma_model_ids():
    client = OpenRouterClient(
        api_key="secret",
        model="google/gemma-4-31b:free",
        fallback_model="google/gemma-4-26b-a4b:free",
    )

    assert client._models_to_try() == [
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "openrouter/free",
    ]
