"""Model chạy local qua Ollama (miễn phí, chạy được khi không có mạng)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import LLMError


class OllamaProvider:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_s: float = 300,
        max_tokens: int = 800,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.name = f"ollama:{model}"

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,  # Ollama ràng buộc đầu ra theo JSON schema
            # num_predict: chặn câu trả lời quá dài (chạy CPU rất chậm); 800 token đủ cho chẩn đoán
            "options": {"temperature": 0.2, "num_predict": self.max_tokens, "num_ctx": 8192},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                reply = json.load(r)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMError(f"không gọi được Ollama: {e}") from None
        try:
            return json.loads(reply["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            raise LLMError(f"Ollama trả về không phải JSON hợp lệ: {e}") from None
