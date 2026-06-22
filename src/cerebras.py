import httpx
from pydantic_settings import BaseSettings

class CerebrasSettings(BaseSettings):
    """Configuration for the Cerebras inference API."""
    CEREBRAS_BASE_URL: str = "https://api.cerebras.ai/v1"
    CEREBRAS_API_KEY: str

    class Config:
        env_file = ".env"
        env_prefix = ""


class CerebrasClient:
    """Async client for Cerebras model calls."""

    def __init__(self):
        self.settings = CerebrasSettings()
        self.client = httpx.AsyncClient(
            base_url=self.settings.CEREBRAS_BASE_URL,
            headers={"Authorization": f"Bearer {self.settings.CEREBRAS_API_KEY}"},
        )

    async def chat(self, messages: list[dict], model: str = "gpt-oss-120b"):
        """Send a chat request to Cerebras."""
        payload = {"model": model, "messages": messages}
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()
