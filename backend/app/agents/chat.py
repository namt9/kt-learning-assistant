"""Chat Agent: hội thoại với sinh viên, chọn agent phù hợp cho từng câu hỏi.

Định tuyến bằng luật (từ khoá tiếng Việt, có hoặc không dấu) nên chạy được khi không có LLM:

    explain_error  "vì sao bài em sai", "lỗi này là gì"        -> Diagnosis Agent
    next_steps     "nên học gì tiếp", "lộ trình"               -> Learning-Path Agent
    concept        "con trỏ là gì", câu nhắc tới một khái niệm -> tri thức trong KG (+ LLM diễn đạt)
    progress       "em tiến bộ chưa", "điểm yếu của em"        -> hồ sơ năng lực
    hint           "gợi ý bài này", "làm sao để bắt đầu"        -> khái niệm của bài + gợi ý
    help           còn lại                                      -> hướng dẫn hỏi gì

LLM (nếu có) chỉ dùng để diễn đạt câu trả lời về khái niệm, dựa trên tri thức KG đưa vào prompt,
và không bao giờ viết lời giải hoàn chỉnh cho bài tập.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel

from ..llm import LLMError
from .learning_path import LearningPathAgent


class ChatLink(BaseModel):
    label: str
    href: str


class ChatReply(BaseModel):
    intent: str
    agent: str  # agent đã trả lời: diagnosis | learning_path | knowledge_graph | profile | help
    text: str
    links: list[ChatLink] = []
    suggestions: list[str] = []  # câu hỏi gợi ý tiếp theo
    llm_provider: str | None = None


def normalize(text: str) -> str:
    """Bỏ dấu tiếng Việt, chữ thường, gộp khoảng trắng: "Con Trỏ" -> "con tro"."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9&%_]+", " ", text).strip()


# Thứ tự quan trọng: ý định đầu tiên khớp sẽ được chọn
INTENTS: list[tuple[str, list[str]]] = [
    (
        "progress",
        [
            "tien bo",
            "nang luc",
            "diem yeu",
            "ho so",
            "dang yeu",
            "yeu phan",
            "yeu gi",
            "yeu o dau",
            "yeu mon",
            "minh yeu",
            "em yeu",
            "toi yeu",
        ],
    ),
    ("next_steps", ["hoc gi", "lo trinh", "tiep theo", "nen on", "on lai gi", "on gi", "luyen gi"]),
    ("hint", ["goi y", "bat dau", "lam sao de", "huong lam", "cach lam", "bi tac"]),
    (
        "explain_error",
        [
            "vi sao",
            "tai sao",
            "sao sai",
            "bi sai",
            "loi gi",
            "loi nay",
            "giai thich loi",
            "sai o dau",
            "bi loi",
            "khong dung",
            "sai cho nao",
        ],
    ),
    ("concept", ["la gi", "nghia la", "khai niem", "dung de lam gi", "giai thich"]),
]

HELP = (
    "Mình có thể giúp bạn:\n"
    "• Giải thích vì sao bài vừa nộp bị sai\n"
    "• Gợi ý nên học gì tiếp dựa trên lỗi bạn hay mắc\n"
    "• Giải thích một khái niệm, ví dụ “con trỏ là gì?”\n"
    "• Gợi ý hướng làm bài đang chọn (không cho lời giải)\n"
    "• Tóm tắt tiến bộ và điểm yếu của bạn"
)
SUGGESTIONS = [
    "Vì sao bài mình sai?",
    "Mình nên học gì tiếp?",
    "Con trỏ là gì?",
    "Gợi ý bài này",
    "Mình đang yếu phần nào?",
]

TYPES = {
    "GIAI_THICH": "Giải thích",
    "VI_DU": "Ví dụ",
    "TRUC_QUAN": "Trực quan",
    "GO_LOI": "Gỡ lỗi",
    "BAI_TAP": "Bài tập",
    "CAU_HOI": "Câu hỏi",
}

CONCEPT_PROMPT = (
    "Bạn là trợ giảng môn Lập trình C/C++ cho sinh viên năm nhất. Trả lời câu hỏi về một khái "
    'niệm bằng tiếng Việt, ngắn gọn (4-7 câu), thân thiện, xưng "bạn". Dựa trên tri thức được '
    "cung cấp; có thể kèm một ví dụ code C rất ngắn minh hoạ khái niệm, nhưng KHÔNG giải hộ bài "
    "tập nào."
)


@dataclass
class _Alias:
    norm: str
    kind: str  # concept | bug
    ref: str


def _rank_actions(kb, concept: str, styles: list[str]) -> list:
    """Hành động sư phạm dạy `concept`, ưu tiên khớp phong cách học rồi dễ trước."""
    acts = (a for a in kb.actions.values() if concept in a.teaches)
    return sorted(acts, key=lambda a: (-len(set(a.styles) & set(styles)), a.level, a.id))


def _kg_link(kb, concept: str) -> ChatLink:
    return ChatLink(
        label=f"Xem “{kb.concepts[concept].name}” trên KG", href=f"/kg-viewer#node={concept}"
    )


class ChatAgent:
    def __init__(self, tutor):
        self.tutor = tutor
        kb = tutor.kb
        aliases = []
        for c in kb.concepts.values():
            aliases.append(_Alias(normalize(c.name), "concept", c.id))
            aliases.append(_Alias(normalize(c.id.replace("_", " ")), "concept", c.id))
        for b in kb.bug_patterns.values():
            aliases.append(_Alias(normalize(b.code), "bug", b.code))
        # tên dài khớp trước ("con tro null" trước "con tro")
        self.aliases = sorted(
            {a.norm: a for a in aliases if len(a.norm) >= 3}.values(), key=lambda a: -len(a.norm)
        )

    # ------------------------------------------------------------ định tuyến

    def detect(self, message: str) -> tuple[str, _Alias | None]:
        msg = f" {normalize(message)} "
        mention = next((a for a in self.aliases if f" {a.norm} " in msg), None)
        for intent, keys in INTENTS:
            if any(f" {k} " in msg for k in keys):
                if intent in ("explain_error", "concept") and mention and mention.kind == "concept":
                    return "concept", mention  # "giải thích con trỏ" là hỏi khái niệm
                return intent, mention
        if mention:
            return "concept", mention
        return "help", None

    def reply(
        self,
        student_id: str,
        message: str,
        submission_id: str | None = None,
        problem_id: str | None = None,
    ) -> ChatReply:
        intent, mention = self.detect(message)
        handler = {
            "explain_error": lambda: self._explain(student_id, submission_id),
            "next_steps": lambda: self._next_steps(student_id),
            "concept": lambda: self._concept(student_id, message, mention),
            "progress": lambda: self._progress(student_id),
            "hint": lambda: self._hint(student_id, problem_id),
            "help": lambda: ChatReply(
                intent="help", agent="help", text=HELP, suggestions=SUGGESTIONS
            ),
        }[intent]
        out = handler()
        self.tutor.storage.log_interaction(
            student_id,
            "chat",
            {
                "message": message,
                "intent": out.intent,
                "agent": out.agent,
            },
        )
        return out

    # ------------------------------------------------------------ từng ý định

    def _latest(self, student_id: str):
        reports = self.tutor.storage.reports(student_id)
        return reports[-1] if reports else None

    def _explain(self, student_id, submission_id) -> ChatReply:
        if submission_id is None:
            latest = self._latest(student_id)
            if latest is None:
                return ChatReply(
                    intent="explain_error",
                    agent="diagnosis",
                    text="Bạn chưa nộp bài nào. Nộp xong mình giải thích lỗi nhé.",
                    suggestions=["Gợi ý bài này"],
                )
            submission_id = latest.submission_id
        try:
            d = self.tutor.diagnose(submission_id)
        except LLMError:
            from ..schemas import DiagnosisMode

            d = self.tutor.diagnose(submission_id, DiagnosisMode.RULE)
        lines = [d.explanation]
        for it in d.items:
            where = f" (dòng {', '.join(map(str, it.lines))})" if it.lines else ""
            lines.append(f"• {it.bug_pattern}{where}: {it.explanation}")
            if it.fix_hint:
                lines.append(f"  Hướng sửa: {it.fix_hint}")
        kb = self.tutor.kb
        concepts = [
            c for c in dict.fromkeys(c for it in d.items for c in it.concepts) if c in kb.concepts
        ][:3]
        return ChatReply(
            intent="explain_error",
            agent="diagnosis",
            text="\n".join(lines),
            llm_provider=d.llm_provider,
            links=[_kg_link(kb, c) for c in concepts],
            suggestions=["Mình nên học gì tiếp?"]
            + [f"{kb.concepts[c].name} là gì?" for c in concepts[:1]],
        )

    def _next_steps(self, student_id) -> ChatReply:
        latest = self._latest(student_id)
        tutor = self.tutor
        bugs = []
        if latest:
            bugs = list(
                dict.fromkeys(f.bug_pattern for f in latest.findings if not f.suppressed_by)
            )
        if not bugs:  # bài gần nhất không lỗi: ôn các lỗi hay mắc nhất
            bugs = [b["bug"] for b in tutor.profile(student_id).top_bugs[:2]]
        if not bugs:
            return ChatReply(
                intent="next_steps",
                agent="learning_path",
                text="Bạn chưa mắc lỗi nào cần ôn. Hãy thử một bài mới khó hơn nhé!",
                suggestions=["Gợi ý bài này"],
            )
        history = tutor._history_bugs(student_id, exclude=latest.submission_id if latest else None)
        agent = LearningPathAgent(tutor.kb, tutor._kg())
        path, _ = agent.plan(student_id, bugs, tutor.styles(student_id), history, max_steps=5)
        kb = tutor.kb
        lines = [f"Dựa trên lỗi {', '.join(bugs)}, mình gợi ý lộ trình sau:"]
        for i, s in enumerate(path.steps, 1):
            extra = f" (bài {s.resource})" if s.resource else ""
            lines.append(f"{i}. {kb.concepts[s.concept].name}: {s.action}{extra}. {s.reason}.")
        return ChatReply(
            intent="next_steps",
            agent="learning_path",
            text="\n".join(lines),
            links=[ChatLink(label="Xem lộ trình trên KG", href=f"/kg-viewer#student={student_id}")],
            suggestions=[f"{kb.concepts[path.steps[0].concept].name} là gì?"] if path.steps else [],
        )

    def _concept(self, student_id, message, mention) -> ChatReply:
        kb = self.tutor.kb
        if mention is None:
            return ChatReply(
                intent="concept",
                agent="knowledge_graph",
                text="Bạn muốn hỏi khái niệm nào? Ví dụ: “con trỏ là gì?”, “cấp phát động là gì?”.",
                suggestions=["Con trỏ là gì?", "Mảng một chiều là gì?"],
            )
        if mention.kind == "bug":
            b = kb.bug_patterns[mention.ref]
            cid = b.concepts[0] if b.concepts else None
            if cid is None:
                return ChatReply(
                    intent="concept", agent="knowledge_graph", text=f"{b.name}: {b.hint}"
                )
        else:
            cid = mention.ref
        c = kb.concepts[cid]
        styles = self.tutor.styles(student_id)
        actions = _rank_actions(kb, cid, styles)[:2]
        prereqs = [kb.concepts[p].name for p in c.prerequisites]
        bugs = [b.name for b in kb.bug_patterns.values() if cid in b.concepts][:3]
        facts = [f"{c.name}: {c.description}"]
        if prereqs:
            facts.append("Cần nắm trước: " + ", ".join(prereqs))
        if bugs:
            facts.append("Lỗi hay gặp liên quan: " + "; ".join(bugs))
        facts += [f"{TYPES.get(a.type, a.type)} “{a.title}”: {a.content}" for a in actions]

        text, provider = None, None
        llm = self.tutor._llm()
        if llm is not None:
            schema = {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            }
            style_note = f"Phong cách học của sinh viên: {', '.join(styles)}." if styles else ""
            user = (
                f"Câu hỏi: {message}\n\nTri thức trong Knowledge Graph:\n- "
                + "\n- ".join(facts)
                + f"\n\n{style_note}"
            )
            try:
                res = llm.generate(CONCEPT_PROMPT, user, schema)
                text, provider = res.data.get("answer") or None, res.provider
            except LLMError:
                pass
        if text is None:  # không có LLM: trả lời thẳng từ tri thức KG
            text = "\n".join(facts)
        return ChatReply(
            intent="concept",
            agent="knowledge_graph",
            text=text,
            llm_provider=provider,
            links=[_kg_link(kb, cid)],
            suggestions=[f"{p} là gì?" for p in prereqs[:2]],
        )

    def _progress(self, student_id) -> ChatReply:
        p = self.tutor.profile(student_id)
        if not p.submissions:
            return ChatReply(
                intent="progress",
                agent="profile",
                text="Bạn chưa nộp bài nào nên mình chưa đánh giá được.",
                suggestions=["Gợi ý bài này"],
            )
        known = [g for g in p.groups if g.mastery is not None]
        lines = [f"Bạn đã nộp {p.submissions} lần, đạt {p.accepted} lần."]
        if known:
            best = max(known, key=lambda g: g.mastery)
            worst = min(known, key=lambda g: g.mastery)
            lines.append(
                f"Mạnh nhất: {best.name} ({best.mastery:.0%}). "
                f"Cần cố gắng: {worst.name} ({worst.mastery:.0%})."
            )
        weak = [c.name for c in p.concepts if c.mastery < 0.5][:3]
        if weak:
            lines.append("Khái niệm nên ôn: " + ", ".join(weak) + ".")
        if p.top_bugs:
            lines.append(
                f"Lỗi bạn hay mắc nhất: {p.top_bugs[0]['name']} ({p.top_bugs[0]['times']} lần)."
            )
        return ChatReply(
            intent="progress",
            agent="profile",
            text="\n".join(lines),
            suggestions=["Mình nên học gì tiếp?"] + [f"{w} là gì?" for w in weak[:1]],
        )

    def _hint(self, student_id, problem_id) -> ChatReply:
        kb = self.tutor.kb
        if problem_id is None or problem_id not in kb.problems:
            return ChatReply(
                intent="hint",
                agent="knowledge_graph",
                text="Bạn chọn một bài tập trước, rồi hỏi lại mình nhé.",
            )
        p = kb.problems[problem_id]
        styles = self.tutor.styles(student_id)
        names = ", ".join(kb.concepts[c].name for c in p.concepts if c in kb.concepts)
        lines = [f"Bài {p.id} ({p.title}) luyện các khái niệm: {names}."]
        for cid in p.concepts:
            # bỏ hành động là bài tập (nhất là chính bài này): chỉ gợi ý hướng nghĩ
            acts = [a for a in _rank_actions(kb, cid, styles) if a.type != "BAI_TAP"]
            if acts:
                lines.append(f"• {kb.concepts[cid].name}: {acts[0].content}")
        lines.append("Hãy tự viết code theo các ý trên; nộp bài xong mình sẽ giúp tìm lỗi.")
        return ChatReply(
            intent="hint",
            agent="knowledge_graph",
            text="\n".join(lines),
            suggestions=[
                f"{kb.concepts[c].name} là gì?" for c in p.concepts[:2] if c in kb.concepts
            ],
        )
