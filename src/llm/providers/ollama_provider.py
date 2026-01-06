from __future__ import annotations
import os
import httpx
from .base import LLMProvider

class OllamaProvider(LLMProvider):
    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1").strip()
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()

    def generate(self, *, system: str, user: str, model: str | None = None) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model or self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.2},
        }

        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()

        return data["message"]["content"]
