"""Backend-local config storage for non-secret metadata and model keys."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

Provider = Literal["openrouter"]
Source = Literal["env", "local_config", "none"]


def _config_dir() -> Path:
    override = os.environ.get("CLAWCODEX_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "ClawCodex"
    return Path.home() / ".clawcodex"


def config_path() -> Path:
    return _config_dir() / "config.json"


def _read_config() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(data: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _env_key(name: str) -> str | None:
    key = os.environ.get(name, "").strip()
    return key or None


def _local_key(provider: Provider = "openrouter") -> str | None:
    value = _read_config().get("model_keys", {}).get(provider, "")
    return value.strip() or None if isinstance(value, str) else None


def get_model_key(provider: Provider = "openrouter") -> str | None:
    return _env_key("OPENROUTER_API_KEY") or _local_key(provider) or _env_key("OPENAI_API_KEY")


def save_model_key(api_key: str, provider: Provider = "openrouter") -> dict[str, object]:
    key = api_key.strip()
    if not key:
        raise ValueError("api_key is required")
    data = _read_config()
    model_keys = data.setdefault("model_keys", {})
    model_keys[provider] = key
    _write_config(data)
    return model_key_status(provider)


def clear_model_key(provider: Provider = "openrouter") -> dict[str, object]:
    data = _read_config()
    model_keys = data.get("model_keys", {})
    if provider in model_keys:
        model_keys.pop(provider)
        data["model_keys"] = model_keys
        _write_config(data)
    return model_key_status(provider)


def model_key_status(provider: Provider = "openrouter") -> dict[str, object]:
    if _env_key("OPENROUTER_API_KEY"):
        return {"configured": True, "provider": provider, "source": "env"}
    if _local_key(provider):
        return {"configured": True, "provider": provider, "source": "local_config"}
    if _env_key("OPENAI_API_KEY"):
        return {"configured": True, "provider": provider, "source": "env"}
    return {"configured": False, "provider": provider, "source": "none"}
