from __future__ import annotations

from typing import Any, cast

import httpx

DEFAULT_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_ROUTER_MODEL = "openrouter/free"
LEGACY_MODEL_ALIASES = {
    "google/gemma-4-31b:free": "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b:free": "google/gemma-4-26b-a4b-it:free",
}


class OpenRouterUnavailable(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = DEFAULT_OPENROUTER_ROUTER_MODEL,
        fallback_model: str = "google/gemma-4-31b-it:free",
        api_url: str = DEFAULT_OPENROUTER_API_URL,
        site_url: str | None = None,
        app_name: str = "Mr Accountable",
        timeout: float = 30.0,
        http_client: Any | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.api_url = api_url
        self.site_url = site_url
        self.app_name = app_name
        self.timeout = timeout
        self.http_client = http_client

    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    async def summarize_messages(self, prompt: str) -> str:
        if not self.enabled():
            raise OpenRouterUnavailable("OpenRouter is not configured.")

        errors: list[str] = []
        for model in self._models_to_try():
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You summarize Telegram group chats. "
                                "Return plain text only, no markdown, no HTML. "
                                "Be factual and concise. Do not invent details. "
                                "Never reveal your reasoning, chain-of-thought, or step-by-step analysis. "
                                "Do not repeat the instructions; output only the final summary."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 350,
                    "temperature": 0.2,
                }
                response = await self._post(payload)
                response.raise_for_status()
                content = self._extract_content(response.json())
                if content:
                    return content
                errors.append(f"{model}: empty response")
            except Exception as exc:
                errors.append(f"{model}: {self._describe_error(exc)}")

        detail = errors[-1] if errors else "unknown OpenRouter failure"
        raise OpenRouterUnavailable(f"OpenRouter request failed ({detail}).")

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_name,
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.http_client is not None:
            return await self.http_client.post(self.api_url, headers=headers, json=payload)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(self.api_url, headers=headers, json=payload)

    def _models_to_try(self) -> list[str]:
        models: list[str] = []
        for candidate in (self.model, self.fallback_model, DEFAULT_OPENROUTER_ROUTER_MODEL):
            normalized = self._normalize_model(candidate)
            if normalized and normalized not in models:
                models.append(normalized)
        return models

    @staticmethod
    def _normalize_model(model: str) -> str:
        cleaned = model.strip()
        return LEGACY_MODEL_ALIASES.get(cleaned, cleaned)

    @staticmethod
    def _describe_error(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            response = cast(httpx.HTTPStatusError, exc).response
            try:
                payload = response.json()
            except Exception:
                payload = None
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    metadata = error.get("metadata")
                    if isinstance(metadata, dict) and metadata.get("raw"):
                        return str(metadata["raw"])
                    if error.get("message"):
                        return str(error["message"])
                if payload.get("message"):
                    return str(payload["message"])
            return str(exc)
        return str(exc)

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
            return "\n".join(parts).strip()
        return ""
