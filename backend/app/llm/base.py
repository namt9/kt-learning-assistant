"""Giao diện chung cho mọi nhà cung cấp LLM.

Agent chỉ gọi `generate_json(system, user, schema)` và nhận về dict đúng JSON schema,
không cần biết phía sau là Claude hay model local qua Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMError(RuntimeError):
    """LLM không trả được kết quả dùng được (lỗi mạng, hết hạn mức, từ chối, sai schema...)."""


@dataclass
class LLMResult:
    data: dict
    provider: str  # tên provider đã trả lời, ví dụ "claude:claude-opus-5-5"
    attempts: list[str] = field(default_factory=list)  # provider đã thử và lỗi (nếu có)


class LLMProvider(Protocol):
    name: str

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        """Trả về dict khớp `schema`; ném LLMError nếu thất bại."""
        ...


class FallbackLLM:
    """Thử lần lượt từng provider, provider đầu tiên trả lời được sẽ được dùng."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("cần ít nhất một provider")
        self.providers = providers

    @property
    def name(self) -> str:
        return " > ".join(p.name for p in self.providers)

    def generate(self, system: str, user: str, schema: dict) -> LLMResult:
        errors: list[str] = []
        for p in self.providers:
            try:
                return LLMResult(p.generate_json(system, user, schema), p.name, errors)
            except LLMError as e:
                errors.append(f"{p.name}: {e}")
        raise LLMError("; ".join(errors))
