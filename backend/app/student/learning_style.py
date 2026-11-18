"""Ước lượng phong cách học: kết hợp bảng hỏi với hành vi tương tác.

Mỗi chiều Felder–Silverman có điểm trong [-1, 1] (dương: visual / active, âm: verbal / reflective).

Bảng hỏi: q = (số câu chọn cực dương - số câu chọn cực âm) / 3.

Hành vi (mỗi sự kiện là một phiếu bầu cho một cực):

- mở một hành động sư phạm  -> +1 cho mỗi phong cách mà hành động đó được gắn (styles trong KG);
- mở Knowledge Graph viewer -> +1 visual;
- hỏi trợ lý giải thích khái niệm -> +0.5 verbal;
- nộp sai rồi nộp lại trong vòng 2 phút mà không xem chẩn đoán / hỏi trợ lý -> +1 active
  (thử - sai);
- nộp sai rồi xem chẩn đoán / hỏi trợ lý trước khi nộp lại -> +1 reflective (suy ngẫm trước).

  b = (dương - âm) / (dương + âm),   trọng số w_b = min(2, số sự kiện / 10)

Điểm kết hợp = (w_q·q + w_b·b) / (w_q + w_b), với w_q = 1 nếu đã làm bảng hỏi. Bảng hỏi là tự đánh
giá một lần, hành vi là quan sát tích luỹ, nên hành vi được nặng tới gấp đôi: vài cú nhấp không lật
được bảng hỏi, nhưng hơn 10 sự kiện nhất quán thì lật được.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..kg.model import KnowledgeBase
from ..schemas import StyleDimension
from .profile import QUESTIONNAIRE

DIMENSIONS = {"visual_verbal": ("visual", "verbal"), "active_reflective": ("active", "reflective")}
POLE_DIM = {pole: dim for dim, poles in DIMENSIONS.items() for pole in poles}
RETRY_WINDOW_S = 120
EVENTS_PER_WEIGHT = 10  # 10 sự kiện = trọng số 1 (bằng bảng hỏi)
MAX_BEHAVIOUR_WEIGHT = 2.0

EVENT_KINDS = {"open_action", "open_kg"}  # sự kiện giao diện gửi lên qua API


def _questionnaire_scores(answers: dict | None) -> dict[str, float]:
    if not answers:
        return {}
    votes: dict[str, float] = defaultdict(float)
    for q in QUESTIONNAIRE:
        choice = answers.get(q["id"])
        if choice in ("a", "b"):
            pole = q[choice][0]
            votes[q["dimension"]] += 1 if DIMENSIONS[q["dimension"]][0] == pole else -1
    return {dim: v / 3 for dim, v in votes.items()}


def _behaviour_votes(timeline: list[dict], kb: KnowledgeBase):
    votes: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[str]] = defaultdict(list)

    def vote(pole: str, weight: float, why: str):
        votes[pole] += weight
        evidence[POLE_DIM[pole]].append(why)

    last_failed_at: datetime | None = None
    consulted = False
    for ev in timeline:
        kind, payload = ev["kind"], ev["payload"]
        at = datetime.fromisoformat(ev["created_at"])
        if kind == "open_action" and payload.get("ref") in kb.actions:
            a = kb.actions[payload["ref"]]
            for pole in a.styles:
                vote(pole, 1, f"mở “{a.title}” ({pole})")
        elif kind == "open_kg":
            vote("visual", 1, "mở Knowledge Graph")
        elif kind == "chat":
            if payload.get("intent") == "concept":
                vote("verbal", 0.5, "hỏi trợ lý giải thích khái niệm")
            consulted = True
        elif kind == "diagnosis":
            consulted = True
        elif kind == "submit":
            if last_failed_at is not None:
                if consulted:
                    vote("reflective", 1, "xem chẩn đoán / hỏi trợ lý trước khi nộp lại")
                elif (at - last_failed_at).total_seconds() <= RETRY_WINDOW_S:
                    vote("active", 1, "nộp lại ngay sau khi sai (thử - sai)")
            failed = payload.get("verdict") != "AC"
            last_failed_at = at if failed else None
            consulted = False
    return votes, evidence


def estimate(answers: dict | None, timeline: list[dict], kb: KnowledgeBase) -> list[StyleDimension]:
    q_scores = _questionnaire_scores(answers)
    votes, evidence = _behaviour_votes(timeline, kb)
    out = []
    for dim, (pos, neg) in DIMENSIONS.items():
        n = votes[pos] + votes[neg]
        b = (votes[pos] - votes[neg]) / n if n else None
        q = q_scores.get(dim)
        wq = 1.0 if q is not None else 0.0
        wb = min(MAX_BEHAVIOUR_WEIGHT, n / EVENTS_PER_WEIGHT) if b is not None else 0.0
        combined = (wq * (q or 0) + wb * (b or 0)) / (wq + wb) if wq + wb else None
        style = None
        if combined is not None and abs(combined) > 1e-9:
            style = pos if combined > 0 else neg
        out.append(StyleDimension(
            dimension=dim,
            questionnaire=None if q is None else round(q, 3),
            behaviour=None if b is None else round(b, 3),
            events=round(n, 2),
            combined=None if combined is None else round(combined, 3),
            style=style,
            evidence=evidence[dim][-5:],
        ))  # fmt: skip
    return out


def effective_styles(detail: list[StyleDimension]) -> list[str] | None:
    styles = [d.style for d in detail if d.style]
    if not styles and all(d.combined is None for d in detail):
        return None
    return styles
