from __future__ import annotations

import os

from fastapi import Header, HTTPException


def _configured_api_keys() -> set[str]:
    raw = os.environ.get("CLAWCODEX_API_KEYS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def get_api_key(x_api_key: str = Header(...)):
    api_keys = _configured_api_keys()
    if not api_keys:
        return x_api_key
    if x_api_key not in api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
