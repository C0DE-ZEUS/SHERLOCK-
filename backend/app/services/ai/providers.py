"""AI model providers behind one small interface.

``OllamaProvider`` talks to a local Ollama server (development default).
``OpenAICompatibleProvider`` talks to any server exposing the OpenAI-style
``/v1/chat/completions`` API (vLLM, llama.cpp server, LM Studio, or a hosted
service) and is only used when explicitly configured. ``DisabledProvider``
is used when AI is turned off. Nothing here ever falls back to a different
provider silently.

Errors carry short, safe messages: never prompt text or model output.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from app.config import Settings, settings


class AIProviderError(Exception):
    """A model call failed. ``kind`` is one of: unavailable, timeout, bad_response, http_error."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class AIStatus:
    available: bool
    provider: str
    model: str
    endpoint_host: str
    is_local: bool  # endpoint is on this machine (loopback)
    message: str


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def is_loopback(url: str) -> bool:
    host = _host(url).lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")


class AIProvider(Protocol):
    name: str
    model: str

    def status(self) -> AIStatus: ...

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Return the model's raw text reply (expected to be JSON)."""
        ...


class DisabledProvider:
    name = "none"
    model = ""

    def status(self) -> AIStatus:
        return AIStatus(False, "none", "", "", True, "AI detection is turned off on this server.")

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        raise AIProviderError("unavailable", "AI detection is turned off.")


class _CachedStatus:
    """Avoid probing the model server on every request."""

    def __init__(self, ttl: float = 15.0) -> None:
        self.ttl = ttl
        self._value: AIStatus | None = None
        self._at = 0.0
        self._lock = threading.Lock()

    def get(self, probe) -> AIStatus:
        with self._lock:
            if self._value is None or time.monotonic() - self._at > self.ttl:
                self._value = probe()
                self._at = time.monotonic()
            return self._value


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._transport = transport
        self._status = _CachedStatus()

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=timeout, transport=self._transport)

    def _probe(self) -> AIStatus:
        host = _host(self.base_url)
        local = is_loopback(self.base_url)
        try:
            with self._client(3.0) as client:
                response = client.get("/api/tags")
            response.raise_for_status()
            names = {m.get("name", "") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError, AttributeError):
            return AIStatus(
                False, self.name, self.model, host, local,
                "Ollama is not reachable. Start Ollama to enable AI detection.",
            )
        wanted = {self.model, f"{self.model}:latest"}
        if not names & wanted:
            return AIStatus(
                False, self.name, self.model, host, local,
                f"Ollama is running but the model '{self.model}' is not installed. "
                f"Run: ollama pull {self.model}",
            )
        return AIStatus(True, self.name, self.model, host, local, f"{self.model} via Ollama")

    def status(self) -> AIStatus:
        return self._status.get(self._probe)

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "think": False,  # Qwen3's reasoning mode is slow on CPU and not needed here
            "format": schema,  # constrained JSON output
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 700},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            with self._client(self.timeout) as client:
                response = client.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise AIProviderError("timeout", "The AI model took too long to respond.") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("unavailable", "Could not reach Ollama.") from exc
        if response.status_code != 200:
            raise AIProviderError("http_error", f"Ollama returned HTTP {response.status_code}.")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AIProviderError("bad_response", "Ollama returned an unexpected response.") from exc
        if not isinstance(content, str):
            raise AIProviderError("bad_response", "Ollama returned an unexpected response.")
        return content


class OpenAICompatibleProvider:
    """Any OpenAI-style chat completions server. Configure it explicitly."""

    name = "openai_compatible"

    def __init__(
        self, base_url: str, model: str, api_key: str | None, timeout: float,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._transport = transport
        self._status = _CachedStatus()

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=self._headers, transport=self._transport
        )

    def _probe(self) -> AIStatus:
        host = _host(self.base_url)
        local = is_loopback(self.base_url)
        if not self.base_url:
            return AIStatus(False, self.name, self.model, "", local, "SHERLOCK_AI_BASE_URL is not set.")
        try:
            with self._client(5.0) as client:
                response = client.get("/models")
            response.raise_for_status()
        except httpx.HTTPError:
            return AIStatus(False, self.name, self.model, host, local, f"The AI server at {host} is not reachable.")
        return AIStatus(True, self.name, self.model, host, local, f"{self.model} via {host}")

    def status(self) -> AIStatus:
        return self._status.get(self._probe)

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system + "\nJSON schema: " + _compact(schema)},
                {"role": "user", "content": user},
            ],
        }
        try:
            with self._client(self.timeout) as client:
                response = client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise AIProviderError("timeout", "The AI model took too long to respond.") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("unavailable", "Could not reach the AI server.") from exc
        if response.status_code != 200:
            raise AIProviderError("http_error", f"The AI server returned HTTP {response.status_code}.")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("bad_response", "The AI server returned an unexpected response.") from exc
        if not isinstance(content, str):
            raise AIProviderError("bad_response", "The AI server returned an unexpected response.")
        return content


def _compact(schema: dict[str, Any]) -> str:
    import json

    return json.dumps(schema, separators=(",", ":"))


def build_provider(cfg: Settings) -> AIProvider:
    if cfg.ai_provider == "ollama":
        return OllamaProvider(cfg.ai_base_url, cfg.ai_model, cfg.ai_timeout_seconds)
    if cfg.ai_provider == "openai_compatible":
        return OpenAICompatibleProvider(cfg.ai_base_url, cfg.ai_model, cfg.ai_api_key, cfg.ai_timeout_seconds)
    return DisabledProvider()


_provider: AIProvider | None = None
_provider_lock = threading.Lock()


def get_provider() -> AIProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = build_provider(settings)
        return _provider


def set_provider(provider: AIProvider | None) -> None:
    """Replace the active provider (used by tests)."""
    global _provider
    with _provider_lock:
        _provider = provider
