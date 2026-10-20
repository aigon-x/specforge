"""Nebius Token Factory client (OpenAI-compatible) with retries and offline fixtures."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .errors import FixtureError, NebiusConfigError, NebiusError
from .fixtures import build_enrichment_fixture

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
# NVIDIA Nemotron is served by Nebius Token Factory; NEBIUS_MODEL may override it.
DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

Transport = Callable[[dict[str, Any]], tuple[int, dict[str, str], str]]


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    mode: str
    attempts: int
    latency_ms: int

    @property
    def offline(self) -> bool:
        return self.mode == "offline"


class _TransportError(Exception):
    pass


def _default_transport(url: str, api_key: str, timeout: float) -> Transport:
    def send(payload: dict[str, Any]) -> tuple[int, dict[str, str], str]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "specforge/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", "replace")
                return response.status, dict(response.headers.items()), text
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            return exc.code, dict(exc.headers.items() if exc.headers else {}), text
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise _TransportError(str(exc)) from exc
    return send


class NebiusClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 20.0,
        max_retries: int = 2,
        backoff: float = 1.0,
        offline: bool = False,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.backoff = max(0.0, float(backoff))
        self.offline = offline
        self._transport = transport or _default_transport(
            f"{self.base_url}/chat/completions", self.api_key, self.timeout
        )

    @classmethod
    def from_env(
        cls,
        mode: str = "auto",
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        backoff: float = 1.0,
        transport: Transport | None = None,
    ) -> "NebiusClient":
        if mode not in ("auto", "live", "offline"):
            raise NebiusError(f"unknown mode {mode!r}", kind="config")
        key = api_key if api_key is not None else os.environ.get("NEBIUS_API_KEY", "")
        if mode == "live" and not key:
            raise NebiusConfigError(
                "live mode requires NEBIUS_API_KEY; use --offline for fixture mode",
                kind="missing_key",
            )
        offline = mode == "offline" or (mode == "auto" and not key)
        env_timeout = os.environ.get("NEBIUS_TIMEOUT")
        if timeout is None:
            try:
                timeout = float(env_timeout) if env_timeout else 20.0
            except ValueError as exc:
                raise NebiusConfigError(
                    f"NEBIUS_TIMEOUT must be a number, got {env_timeout!r}", kind="config"
                ) from exc
        if timeout <= 0:
            raise NebiusConfigError("timeout must be positive", kind="config")
        return cls(
            api_key=key,
            base_url=os.environ.get("NEBIUS_API_BASE", DEFAULT_BASE_URL),
            model=os.environ.get("NEBIUS_MODEL") or DEFAULT_MODEL,
            timeout=timeout,
            max_retries=max_retries,
            backoff=backoff,
            offline=offline,
            transport=transport,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "mode": "offline" if self.offline else "live",
            "provider": "nebius-token-factory",
            "model": self.model,
            "base_url": self.base_url,
            "timeout_s": self.timeout,
            "max_retries": self.max_retries,
        }

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        task: str = "enrich",
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> Completion:
        if self.offline:
            return self._offline(task, messages)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return self._live(payload)

    def _offline(self, task: str, messages: list[dict[str, str]]) -> Completion:
        if task != "enrich":
            raise FixtureError(f"fixture has no task {task!r}", kind="fixture")
        content = json.dumps(
            build_enrichment_fixture(messages), sort_keys=True, ensure_ascii=False
        )
        return Completion(
            content=content,
            model=f"fixture:{self.model}",
            mode="offline",
            attempts=0,
            latency_ms=0,
        )

    def _live(self, payload: dict[str, Any]) -> Completion:
        started = time.monotonic()
        attempts = 0
        last_error = ""
        for attempt in range(1, self.max_retries + 2):
            attempts = attempt
            try:
                status, headers, body = self._transport(payload)
            except _TransportError as exc:
                last_error = f"transport error: {exc}"
                status, headers, body = 0, {}, ""
            else:
                if 200 <= status < 300:
                    return self._parse(body, attempts, started)
                last_error = f"HTTP {status}: {body[:300]}"
                if not (status in (408, 409, 425, 429) or status >= 500):
                    raise NebiusError(last_error, kind="http", status=status, attempts=attempts)
            if attempt <= self.max_retries:
                time.sleep(self._delay(headers, attempt))
        raise NebiusError(
            f"retries exhausted after {attempts} attempts; last: {last_error}",
            kind="retry_exhausted",
            status=None,
            attempts=attempts,
        )

    def _delay(self, headers: dict[str, str], attempt: int) -> float:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return min(30.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
        return min(30.0, self.backoff * (2 ** (attempt - 1)))

    def _parse(self, body: str, attempts: int, started: float) -> Completion:
        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise NebiusError(f"invalid completion payload: {exc}", kind="invalid_response",
                              attempts=attempts) from exc
        if not isinstance(content, str) or not content.strip():
            raise NebiusError("model returned empty content", kind="invalid_response",
                              attempts=attempts)
        return Completion(
            content=content,
            model=str(data.get("model") or self.model),
            mode="live",
            attempts=attempts,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
