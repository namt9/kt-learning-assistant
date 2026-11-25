"""Model GPT/DeepSeek triển khai trên Azure (Azure OpenAI / Foundry), gọi thẳng REST.

Dùng chung key và resource với Claude trên Foundry nếu không đặt riêng AZURE_OPENAI_*.
Đầu ra ràng buộc bằng `response_format: json_schema`; ở chế độ không strict vì schema của
dự án có trường tuỳ chọn.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import LLMError

API_VERSION = "2024-10-21"


class AzureOpenAIProvider:
    def __init__(
        self,
        deployment: str,
        endpoint: str,
        api_key: str,
        timeout_s: float = 180,
        max_tokens: int = 16000,
    ):
        if not endpoint or not api_key:
            raise ValueError("thiếu AZURE_OPENAI_ENDPOINT hoặc khoá Azure")
        self.deployment = deployment
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.name = f"azure:{deployment}"

    def _body(self, system: str, user: str, schema: dict) -> dict:
        return {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # model suy luận (gpt-5.x) không nhận temperature/max_tokens, chỉ nhận
            # max_completion_tokens (gồm cả token suy luận)
            "max_completion_tokens": self.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": False},
            },
        }

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
            f"?api-version={API_VERSION}"
        )
        req = urllib.request.Request(
            url,
            json.dumps(self._body(system, user, schema)).encode(),
            {"Content-Type": "application/json", "api-key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                reply = json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise LLMError(f"lỗi Azure {e.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMError(f"không gọi được Azure: {e}") from None
        try:
            choice = reply["choices"][0]
            if choice.get("finish_reason") == "length":
                raise LLMError("câu trả lời bị cắt do hết max_completion_tokens")
            return json.loads(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            raise LLMError(f"Azure trả về không phải JSON hợp lệ: {e}") from None
