import httpx
from pydantic_settings import BaseSettings

class OpenRouterSettings(BaseSettings):
    """Configuration for OpenRouter API."""
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    class Config:
        env_file = ".env"
        env_prefix = ""

class OpenRouterClient:
    """Async client for OpenRouter model calls."""
    def __init__(self):
        self.settings = OpenRouterSettings()
        self.client = httpx.AsyncClient(
            base_url=self.settings.OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost:8000",  # Optional, for per-provider analytics
                "X-Title": "ClawCodex"  # Optional, shows in OpenRouter dropdown
            }
        )

    async def chat(self, messages: list[dict], model: str = "mistralai/mistral-7b-instruct"):
        """Send a chat request to OpenRouter."""
        payload = {
            "model": model,
            "messages": messages
        }
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()