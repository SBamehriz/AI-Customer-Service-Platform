"""LLM provider adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-2.0-flash",
}

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}


class ProviderError(RuntimeError):
    """Raised when a provider is reachable but rejects or fails the request."""


@dataclass(slots=True)
class Completion:
    text: str
    model: str
    provider: str


class BaseProvider:
    name = "none"
    available = False

    def __init__(self, api_key: str = "", model: str = "", base_url: str = "") -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODELS.get(self.name, "")
        self.base_url = (base_url or DEFAULT_BASE_URLS.get(self.name, "")).rstrip("/")

    async def complete(
        self, system: str, prompt: str, *, max_tokens: int = 600, temperature: float = 0.2
    ) -> Completion:
        raise NotImplementedError

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input, or an empty list when unsupported."""
        return []

    async def _post(self, url: str, *, headers: dict, json: dict) -> dict:
        timeout = httpx.Timeout(settings.LLM_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=json)
            if response.status_code >= 400:
                raise ProviderError(f"{self.name} returned {response.status_code}: {response.text[:300]}")
            return response.json()


class NullProvider(BaseProvider):
    """Used when no provider is configured."""

    name = "none"
    available = False

    async def complete(self, system: str, prompt: str, **_: object) -> Completion:
        raise ProviderError("No LLM provider configured (set LLM_PROVIDER and LLM_API_KEY)")


class OpenAIProvider(BaseProvider):
    """OpenAI chat completions, and anything that speaks the same protocol."""

    name = "openai"
    available = True

    async def complete(
        self, system: str, prompt: str, *, max_tokens: int = 600, temperature: float = 0.2
    ) -> Completion:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = await self._post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected OpenAI response shape: {exc}") from exc
        return Completion(text=text.strip(), model=self.model, provider=self.name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not settings.EMBEDDING_MODEL or not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = await self._post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json={"model": settings.EMBEDDING_MODEL, "input": texts},
        )
        return [item["embedding"] for item in data.get("data", [])]


class AnthropicProvider(BaseProvider):
    """Claude Messages API."""

    name = "anthropic"
    available = True

    async def complete(
        self, system: str, prompt: str, *, max_tokens: int = 600, temperature: float = 0.2
    ) -> Completion:
        data = await self._post(
            f"{self.base_url}/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        blocks = data.get("content", [])
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        return Completion(text=text.strip(), model=self.model, provider=self.name)


class GeminiProvider(BaseProvider):
    """Google Generative Language API."""

    name = "gemini"
    available = True

    async def complete(
        self, system: str, prompt: str, *, max_tokens: int = 600, temperature: float = 0.2
    ) -> Completion:
        data = await self._post(
            f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature,
                },
            },
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected Gemini response shape: {exc}") from exc
        return Completion(text=text.strip(), model=self.model, provider=self.name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not settings.EMBEDDING_MODEL or not texts:
            return []
        model = settings.EMBEDDING_MODEL
        data = await self._post(
            f"{self.base_url}/models/{model}:batchEmbedContents?key={self.api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "requests": [
                    {"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
                    for text in texts
                ]
            },
        )
        return [item["values"] for item in data.get("embeddings", [])]


_PROVIDERS: dict[str, type[BaseProvider]] = {
    "none": NullProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}

_cached: Optional[BaseProvider] = None

_workspace_cache: dict[tuple, BaseProvider] = {}


def build_provider(
    name: str, api_key: str = "", model: str = "", base_url: str = ""
) -> BaseProvider:
    """Construct a provider without touching any cache."""
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        logger.warning("Unknown LLM provider %r, falling back to none", name)
        provider_cls = NullProvider
    return provider_cls(api_key=api_key, model=model, base_url=base_url)


def get_provider(workspace: Optional[object] = None) -> BaseProvider:
    """The provider to use, preferring what this workspace configured."""
    if workspace is not None and not settings.llm_enabled:
        config = getattr(workspace, "ai_config", None) or {}
        key = _unseal_key(config)
        if key and config.get("provider") not in (None, "", "none"):
            signature = (
                config.get("provider"),
                key,
                config.get("model", ""),
                config.get("base_url", ""),
            )
            if signature not in _workspace_cache:
                _workspace_cache.clear() if len(_workspace_cache) > 32 else None
                _workspace_cache[signature] = build_provider(
                    config["provider"],
                    api_key=key,
                    model=config.get("model", ""),
                    base_url=config.get("base_url", ""),
                )
            return _workspace_cache[signature]

    global _cached
    if _cached is None:
        name = settings.LLM_PROVIDER if settings.llm_enabled else "none"
        _cached = build_provider(
            name,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
        )
    return _cached


def _unseal_key(config: dict) -> str:
    from ..crypto import unseal

    return unseal(config.get("api_key", "")) or ""


def forget_workspace_providers() -> None:
    """Drop cached workspace providers, after a credential changes."""
    _workspace_cache.clear()
