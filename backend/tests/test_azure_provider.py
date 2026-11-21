"""Azure OpenAI: dựng yêu cầu và đọc kết quả (không gọi API thật)."""

import json

import pytest

from backend.app.llm import azure_openai, make_llm
from backend.app.llm.base import LLMError


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.body).encode()


def _fake(monkeypatch, reply):
    sent = {}

    def urlopen(req, timeout):
        sent["url"], sent["headers"], sent["body"] = req.full_url, req.headers, json.loads(req.data)
        return _Resp(reply)

    monkeypatch.setattr(azure_openai.urllib.request, "urlopen", urlopen)
    return sent


def test_shares_foundry_key_and_resource(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "res")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "k")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.5")
    p = make_llm("azure").providers[0]
    sent = _fake(monkeypatch, {"choices": [{"message": {"content": '{"a": 1}'}}]})
    assert p.generate_json("s", "u", {"type": "object"}) == {"a": 1}
    assert sent["url"].startswith("https://res.openai.azure.com/openai/deployments/gpt-5.5/")
    assert sent["headers"]["Api-key"] == "k"
    assert sent["body"]["response_format"]["type"] == "json_schema"
    assert p.name == "azure:gpt-5.5"


def test_truncated_reply_is_an_error(monkeypatch):
    p = azure_openai.AzureOpenAIProvider("d", "https://x", "k")
    _fake(monkeypatch, {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]})
    with pytest.raises(LLMError, match="bị cắt"):
        p.generate_json("s", "u", {})
