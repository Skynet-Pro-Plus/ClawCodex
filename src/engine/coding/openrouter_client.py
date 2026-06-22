"""Minimal OpenRouter/OpenAI-compatible client for strict JSON code proposals."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..settings.local_config import get_model_key


class ModelNotConfigured(RuntimeError):
    """Raised when no compatible model credentials are available."""


class ModelResponseError(RuntimeError):
    """Raised when the model returns an unusable response."""


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    base_url: str
    model: str


def load_openrouter_config(model: str) -> OpenRouterConfig:
    api_key = get_model_key("openrouter") or ""
    if not api_key:
        raise ModelNotConfigured(
            "OpenRouter key is missing. Open Settings to add and save your API key."
        )
    base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    return OpenRouterConfig(api_key=api_key, base_url=base_url, model=model)


def request_code_json(model: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return request_code_json_with_usage(model, system_prompt, user_prompt)["json"]


def request_code_json_with_usage(model: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    config = load_openrouter_config(model)
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "ClawCodex",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        if exc.code in {401, 403}:
            raise ModelNotConfigured(
                "OpenRouter authentication failed. Open Settings, save a valid OpenRouter key, then run the mission again."
            ) from exc
        raise ModelResponseError(f"model request failed: HTTP {exc.code} {body[:500]}") from exc
    except OSError as exc:
        raise ModelResponseError(f"model request failed: {exc}") from exc
    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise ModelResponseError("model response did not include message content")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ModelResponseError("model response was not valid JSON") from exc
    return {"json": parsed, "usage": data.get("usage") or {}, "model": data.get("model") or model}


def list_openrouter_models(api_key_override: str | None = None) -> list[dict[str, Any]]:
    base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    headers = {"Content-Type": "application/json"}
    api_key = api_key_override or get_model_key("openrouter")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise ModelNotConfigured("OpenRouter rejected this API key. Check the key and try again.") from exc
        body = exc.read().decode("utf-8", errors="ignore")
        raise ModelResponseError(f"model list request failed: HTTP {exc.code} {body[:300]}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelResponseError(f"model list request failed: {exc}") from exc
    models = data.get("data", [])
    if not isinstance(models, list):
        raise ModelResponseError("model list response did not include data")
    return [
        {
            "id": str(item.get("id", "")),
            "name": str(item.get("name") or item.get("id") or ""),
            "company": str(item.get("id", "")).split("/", 1)[0],
            "released_at": _format_release_date(item.get("created")),
            "context_length": item.get("context_length"),
            "pricing": item.get("pricing") or {},
        }
        for item in models
        if item.get("id")
    ]


def validate_openrouter_key(api_key: str) -> int:
    key = api_key.strip()
    if not key:
        raise ModelNotConfigured("OpenRouter API key is required.")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/auth/key",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise ModelNotConfigured("OpenRouter rejected this API key. Check the key and try again.") from exc
        body = exc.read().decode("utf-8", errors="ignore")
        raise ModelResponseError(f"key validation failed: HTTP {exc.code} {body[:300]}") from exc
    except OSError as exc:
        raise ModelResponseError(f"key validation failed: {exc}") from exc
    return len(list_openrouter_models(api_key_override=key))


def _format_release_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return str(value) or None
    return datetime.fromtimestamp(timestamp, UTC).date().isoformat()
