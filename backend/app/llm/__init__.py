"""Lớp trung gian LLM: Claude (mặc định) và Ollama (dự phòng khi mất mạng / hết hạn mức).

Chọn bằng biến môi trường LLM_PROVIDERS, theo thứ tự ưu tiên, ví dụ "claude,ollama".
"""

from __future__ import annotations

import os

from .base import FallbackLLM, LLMError, LLMProvider, LLMResult

__all__ = ["FallbackLLM", "LLMError", "LLMProvider", "LLMResult", "make_llm"]


def make_llm(spec: str | None = None) -> FallbackLLM | None:
    """Tạo chuỗi provider từ LLM_PROVIDERS. Trả về None nếu không cấu hình provider nào."""
    spec = spec if spec is not None else os.getenv("LLM_PROVIDERS", "claude,ollama")
    providers: list[LLMProvider] = []
    for name in (s.strip() for s in spec.split(",") if s.strip()):
        if name == "claude":
            try:
                from .claude import ClaudeProvider

                providers.append(
                    ClaudeProvider(
                        model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
                        effort=os.getenv("CLAUDE_EFFORT", "medium"),
                    )
                )
            except ImportError:  # chưa cài gói anthropic -> bỏ qua, dùng provider sau
                continue
        elif name == "ollama":
            from .ollama import OllamaProvider

            providers.append(
                OllamaProvider(
                    model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
                    base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
                )
            )
        else:
            raise ValueError(f"LLM provider không hỗ trợ: {name}")
    return FallbackLLM(providers) if providers else None
