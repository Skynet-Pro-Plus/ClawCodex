#!/usr/bin/env python
"""
Simple CLI for chatting with the ClawCodex headless API server.

This version works without requiring any external API keys. If a real model
provider (Cerebras or OpenRouter) is configured, it will be used; otherwise the
script falls back to a local echo‑only mode that simply returns the user’s
message prefixed with “(local echo)”.

Usage:
    1. Start the API server (if you want to use the HTTP endpoints):
       uvicorn src.server.app:app --host 0.0.0.0 --port 8000

    2. In a separate terminal, run this script:
       python clawcodex_chat.py
"""

import asyncio
import json
import os
import sys

# Ensure the repository root is on the Python path so that `src` can be imported.
repo_root = os.path.abspath(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# ----------------------------------------------------------------------
# Helper: a very small fallback client that mimics the ModelClient API.
# ----------------------------------------------------------------------
class _LocalEchoClient:
    async def chat(self, messages, model: str = None):
        # Return a simple echo response that matches the shape of the real APIs.
        user_msg = messages[0].get("content", "")
        return {
            "id": "local-echo",
            "object": "chat.completion",
            "created": 0,
            "model": model or "local-echo",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"(local echo) {user_msg}"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(user_msg.split()),
                "completion_tokens": len(user_msg.split()),
                "total_tokens": len(user_msg.split()) * 2
            }
        }

# Try to import the real ModelClient. If it fails (e.g. missing env vars),
# fall back to the local echo client.
try:
    from src.model_client import ModelClient
    # Instantiate; any missing configuration will raise at call time.
    client = ModelClient()
except Exception as e:
    print("[info] Real model client could not be initialized:", e)
    print("[info] Falling back to local echo mode (no external API calls).")
    client = _LocalEchoClient()

async def chat_loop() -> None:
    print("ClawCodex chat CLI – type a message and press Enter (empty line to quit).")
    while True:
        try:
            user_input = input("> ")
        except EOFError:
            break
        if not user_input:
            break

        messages = [{"role": "user", "content": user_input}]
        try:
            response = await client.chat(messages)
        except Exception as exc:
            print(f"[error] Failed to get a response: {exc}")
            continue

        print(json.dumps(response, indent=2))

if __name__ == "__main__":
    asyncio.run(chat_loop())
