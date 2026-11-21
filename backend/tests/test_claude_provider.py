"""Claude: chọn client Anthropic hay Foundry theo biến môi trường (không gọi API thật)."""

import pytest

pytest.importorskip("anthropic")

from backend.app.llm.claude import ClaudeProvider  # noqa: E402


def test_first_party_uses_server_side_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_RESOURCE", raising=False)
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    p = ClaudeProvider(model="claude-sonnet-4-6")
    assert not p.foundry
    req = p._request("s", "u", {"type": "object"})
    assert req["fallbacks"] == "default" and req["model"] == "claude-sonnet-4-6"


def test_foundry_client_without_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "my-res")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "test")
    p = ClaudeProvider(model="claude-sonnet-4-6")
    assert p.foundry and type(p.client).__name__ == "AnthropicFoundry"
    req = p._request("s", "u", {"type": "object"})
    assert "fallbacks" not in req and "betas" not in req
    assert req["output_config"]["format"]["type"] == "json_schema"
