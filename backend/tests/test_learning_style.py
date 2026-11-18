"""Ước lượng phong cách học từ bảng hỏi và hành vi tương tác."""

from datetime import datetime, timedelta

import pytest

from backend.app.config import ROOT
from backend.app.kg.model import KnowledgeBase
from backend.app.student.learning_style import effective_styles, estimate
from backend.app.student.profile import QUESTIONNAIRE

VISUAL_ACTIVE = "PA_KHOI_TAO_TRUC_QUAN"  # styles: [visual, active]
VERBAL_REFLECTIVE = "PA_KHOI_TAO_GIAI_THICH"  # styles: [verbal, reflective]
T0 = datetime(2026, 11, 18, 8, 0, 0)


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(ROOT / "knowledge", ROOT / "data" / "problems")


def timeline(*events):
    """events: (giây kể từ T0, kind, payload)."""
    return [{"kind": k, "payload": p, "created_at": (T0 + timedelta(seconds=s)).isoformat(sep=" ")}
            for s, k, p in events]  # fmt: skip


def dims(detail):
    return {d.dimension: d for d in detail}


ALL_B = {q["id"]: "b" for q in QUESTIONNAIRE}  # verbal + reflective


def test_nothing_known(kb):
    detail = estimate(None, [], kb)
    assert all(d.combined is None and d.style is None for d in detail)
    assert effective_styles(detail) is None


def test_questionnaire_only(kb):
    d = dims(estimate(ALL_B, [], kb))
    assert d["visual_verbal"].questionnaire == -1 and d["visual_verbal"].style == "verbal"
    assert d["active_reflective"].style == "reflective"


def test_few_clicks_do_not_override_questionnaire(kb):
    clicks = timeline(*[(i, "open_action", {"ref": VISUAL_ACTIVE}) for i in range(3)])
    d = dims(estimate(ALL_B, clicks, kb))
    assert d["visual_verbal"].behaviour == 1 and d["visual_verbal"].events == 3
    assert d["visual_verbal"].style == "verbal"  # 3 sự kiện: trọng số 0.3 < bảng hỏi


def test_consistent_behaviour_outweighs_questionnaire(kb):
    clicks = timeline(*[(i, "open_action", {"ref": VISUAL_ACTIVE}) for i in range(12)])
    clicks += timeline((20, "open_kg", {"ref": None}))
    d = dims(estimate(ALL_B, clicks, kb))
    assert d["visual_verbal"].style == "visual"
    assert any("Knowledge Graph" in e for e in d["visual_verbal"].evidence)


def test_behaviour_only(kb):
    d = dims(estimate(None, timeline((0, "open_action", {"ref": VERBAL_REFLECTIVE})), kb))
    assert d["visual_verbal"].style == "verbal" and d["visual_verbal"].questionnaire is None


def test_retry_patterns(kb):
    wa = {"verdict": "WA"}
    trial_and_error = timeline((0, "submit", wa), (40, "submit", wa), (70, "submit", wa))
    d = dims(estimate(None, trial_and_error, kb))["active_reflective"]
    assert d.style == "active" and d.events == 2

    think_first = timeline((0, "submit", wa), (30, "diagnosis", {}), (60, "submit", wa),
                           (90, "chat", {"intent": "concept"}), (400, "submit", {"verdict": "AC"}))  # fmt: skip
    d = dims(estimate(None, think_first, kb))
    assert d["active_reflective"].style == "reflective" and d["active_reflective"].events == 2
    assert d["visual_verbal"].style == "verbal"  # hỏi giải thích khái niệm

    slow_retry = timeline((0, "submit", wa), (900, "submit", wa))  # quá 2 phút: không kết luận
    assert dims(estimate(None, slow_retry, kb))["active_reflective"].events == 0
    after_ac = timeline((0, "submit", {"verdict": "AC"}), (10, "submit", wa))
    assert dims(estimate(None, after_ac, kb))["active_reflective"].events == 0


def test_events_api_changes_effective_style(client):
    sid = "sv_style"
    client.put(f"/students/{sid}/learning-style", json=ALL_B)
    assert client.get(f"/students/{sid}/profile").json()["styles"] == ["verbal", "reflective"]
    for _ in range(15):
        r = client.post(
            f"/students/{sid}/events", json={"kind": "open_action", "ref": VISUAL_ACTIVE}
        )
        assert r.status_code == 204
    prof = client.get(f"/students/{sid}/profile").json()
    assert prof["styles"] == ["visual", "active"]
    vv = next(d for d in prof["style_detail"] if d["dimension"] == "visual_verbal")
    assert vv["questionnaire"] == -1 and vv["behaviour"] == 1 and vv["evidence"]
    bad = client.post(f"/students/{sid}/events", json={"kind": "hack", "ref": "x"})
    assert bad.status_code == 422
