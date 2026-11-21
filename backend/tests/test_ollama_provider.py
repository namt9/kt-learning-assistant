"""Ollama: tuỳ chọn gửi đi (không cần Ollama chạy thật)."""

import json

from backend.app.llm import ollama
from backend.app.llm.ollama import OllamaProvider


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.body).encode()


def _sent_options(monkeypatch, provider):
    sent = {}

    def fake_urlopen(req, timeout):
        sent.update(json.loads(req.data))
        return _Resp({"message": {"content": '{"ok": true}'}})

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)
    assert provider.generate_json("s", "u", {"type": "object"}) == {"ok": True}
    return sent["options"]


def test_num_thread_only_sent_when_set(monkeypatch):
    assert "num_thread" not in _sent_options(monkeypatch, OllamaProvider("m"))
    assert _sent_options(monkeypatch, OllamaProvider("m", num_thread=6))["num_thread"] == 6


def test_env_sets_num_thread(monkeypatch):
    from backend.app.llm import make_llm

    monkeypatch.setenv("LLM_PROVIDERS", "ollama")
    monkeypatch.setenv("OLLAMA_NUM_THREAD", "6")
    llm = make_llm()
    assert llm.providers[0].num_thread == 6
