import os
from typing import Optional

from .cerebras import CerebrasClient
try:
    from .openrouter_client import OpenRouterClient
except ImportError:
    OpenRouterClient = None  # type: ignore


class ModelClient:
    """Unified interface for model providers (OpenRouter or Cerebras)."""

    def __init__(self):
        provider = os.getenv("CLAW_PROVIDER", os.getenv("MODEL_PROVIDER", "openrouter")).lower()
        if provider == "cerebras":
            self.client = CerebrasClient()
        else:
            if OpenRouterClient is None:
                raise RuntimeError("OpenRouter client not available.")
            self.client = OpenRouterClient()

    async def chat(self, messages: list[dict], model: Optional[str] = None):
        """Delegate chat request to the selected provider."""
        default_model = "gpt-oss-120b" if os.getenv("CLAW_PROVIDER", os.getenv("MODEL_PROVIDER", "")).lower() == "cerebras" else "mistralai/mistral-7b-instruct"
        return await self.client.chat(messages, model=model or default_model)
