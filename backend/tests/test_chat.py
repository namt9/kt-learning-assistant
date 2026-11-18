"""Chat Agent: định tuyến ý định và trả lời dựa trên KG / các agent khác."""

import pytest

from backend.app.agents.chat import ChatAgent, normalize
from backend.app.llm import FallbackLLM

MISSING_AMP = (
    '#include <stdio.h>\nint main(void){int n; scanf("%d", n); printf("%d\\n", n); return 0;}'
)


@pytest.fixture
def chat(client):
    return ChatAgent(client.app.state.tutor)


def test_normalize_vietnamese():
    assert normalize("Con TRỎ là gì?") == "con tro la gi"
    assert normalize("Địa chỉ  bộ nhớ") == "dia chi bo nho"


@pytest.mark.parametrize(("message", "intent", "ref"), [
    ("Vì sao bài em bị sai?", "explain_error", None),
    ("tai sao bai em sai vay", "explain_error", None),  # gõ không dấu
    ("Con trỏ là gì?", "concept", "con_tro"),
    ("giai thich con tro null cho em", "concept", "con_tro_null"),  # khớp tên dài nhất
    ("cấp phát động dùng để làm gì", "concept", "cap_phat_dong"),
    ("MEM_LEAK là gì", "concept", "MEM_LEAK"),
    ("Em nên học gì tiếp theo?", "next_steps", None),
    ("Em đang yếu phần nào?", "progress", None),
    ("Gợi ý bài này với", "hint", None),
    ("xin chào", "help", None),
])  # fmt: skip
def test_intent_routing(chat, message, intent, ref):
    got, mention = chat.detect(message)
    assert got == intent
    if ref:
        assert mention is not None and mention.ref == ref


def submit(client, sid="sv_c"):
    body = {"student_id": sid, "problem_id": "P001", "source_code": MISSING_AMP}
    return client.post("/tutor/submit", json=body).json()


def ask(client, message, **ctx):
    r = client.post("/tutor/chat", json={"student_id": "sv_c", "message": message, **ctx})
    assert r.status_code == 200, r.text
    return r.json()


def test_chat_before_any_submission(client):
    assert "chưa nộp" in ask(client, "Vì sao bài em sai?")["text"]
    assert "chưa nộp" in ask(client, "Em tiến bộ chưa?")["text"]


def test_chat_flow_after_submission(client):
    submit(client)
    r = ask(client, "Vì sao bài em sai?")
    assert r["agent"] == "diagnosis" and "SCANF_MISSING_AMP" in r["text"]
    assert any("/kg-viewer#node=" in link["href"] for link in r["links"])

    r = ask(client, "Em nên học gì tiếp?")
    assert r["agent"] == "learning_path" and "1." in r["text"]

    r = ask(client, "Em đang yếu phần nào?")
    assert r["agent"] == "profile" and "1 lần" in r["text"]

    r = ask(client, "Gợi ý bài này", problem_id="P001")
    assert r["agent"] == "knowledge_graph" and "P001" in r["text"]

    kinds = [i["kind"] for i in client.get("/students/sv_c/interactions").json()]
    assert kinds.count("chat") == 4


def test_concept_answer_without_and_with_llm(client):
    r = ask(client, "con trỏ là gì")
    assert r["llm_provider"] is None and "Con trỏ:" in r["text"]  # tri thức thẳng từ KG

    class FakeLLM:
        name = "fake"

        def __init__(self):
            self.prompt = None

        def generate_json(self, system, user, schema):
            self.prompt = user
            return {"answer": "Con trỏ là biến lưu địa chỉ."}

    fake = FakeLLM()
    client.app.state.llm = FallbackLLM([fake])
    r = ask(client, "con trỏ là gì")
    assert r["llm_provider"] == "fake" and r["text"] == "Con trỏ là biến lưu địa chỉ."
    assert "Tri thức trong Knowledge Graph" in fake.prompt and "Con trỏ:" in fake.prompt


def test_chat_validation(client):
    bad = client.post("/tutor/chat", json={"student_id": "sv", "message": ""})
    assert bad.status_code == 422
