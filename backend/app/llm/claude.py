"""Claude qua Anthropic SDK.

Đầu ra bị ràng buộc bằng structured outputs (`output_config.format`), nên luôn là JSON
đúng schema. Bật fallback phía server: nếu model từ chối vì bộ lọc an toàn, API tự chạy
lại yêu cầu trên model dự phòng.
"""

from __future__ import annotations

import json

from .base import LLMError


class ClaudeProvider:
    def __init__(
        self, model: str = "claude-opus-5-5", effort: str = "medium", timeout_s: float = 120
    ):
        import anthropic  # chỉ cần cài khi thật sự dùng Claude

        self._anthropic = anthropic
        # Đọc khoá từ ANTHROPIC_API_KEY (hoặc profile `ant auth login`)
        self.client = anthropic.Anthropic(timeout=timeout_s, max_retries=2)
        self.model = model
        self.effort = effort
        self.name = f"claude:{model}"

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        a = self._anthropic
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError:
            raise LLMError("sai hoặc thiếu ANTHROPIC_API_KEY") from None
        except a.RateLimitError:
            raise LLMError("vượt hạn mức gọi API (429)") from None
        except a.APIStatusError as e:
            raise LLMError(f"lỗi API {e.status_code}: {e.message}") from None
        except a.APIConnectionError:
            raise LLMError("không kết nối được tới API Claude") from None
        except a.AnthropicError as e:
            raise LLMError(f"lỗi SDK Anthropic: {e}") from None
        except TypeError as e:  # SDK ném TypeError khi không tìm thấy key/profile nào
            if "authentication" not in str(e):
                raise
            raise LLMError("chưa cấu hình ANTHROPIC_API_KEY") from None

        if resp.stop_reason == "refusal":
            raise LLMError("model từ chối trả lời")
        if resp.stop_reason == "max_tokens":
            raise LLMError("câu trả lời bị cắt do hết max_tokens")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise LLMError("không có nội dung văn bản trong câu trả lời")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"JSON không hợp lệ: {e}") from None
