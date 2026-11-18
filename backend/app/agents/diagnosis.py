"""Diagnosis Agent: chẩn đoán lỗi và giải thích cho sinh viên.

Ba chế độ, cũng là ba cấu hình đem so sánh trong phần thực nghiệm:

- rule     : luật (gcc/cppcheck/sanitizer/luật tự viết) xác định lỗi, giải thích lấy từ gợi ý
             cố định và hành động sư phạm trong KG. Không gọi LLM.
- llm_only : LLM đọc code và kết quả chấm, tự tìm lỗi rồi giải thích. Không dùng luật, KG.
- hybrid   : luật xác định lỗi (nguồn sự thật), KG cấp khái niệm + cách sửa, LLM chỉ được
             giải thích đúng các lỗi đó. Mã lỗi ngoài danh sách bị chặn bởi JSON schema
             và bị lọc lại trong code (phòng model local không tuân thủ schema).

LLM lỗi hoặc chưa cấu hình thì hybrid tự lùi về rule, kèm ghi chú trong `notes`.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Protocol

from ..llm import FallbackLLM, LLMError
from ..problems import ProblemData as ProblemFiles
from ..rules.catalog import Catalog
from ..schemas import (
    Diagnosis,
    DiagnosisItem,
    DiagnosisMode,
    Finding,
    SubmissionReport,
    Verdict,
)


class KnowledgeSource(Protocol):
    """Phần KGQueries mà agent cần (có thể thay bằng bản giả khi test)."""

    def concepts_for_bugs(self, bug_codes: list[str]) -> list[dict]: ...

    def remediation(self, bug_code: str, styles: list[str] | None = None, limit: int = 3): ...


SYSTEM_PROMPT = """Bạn là trợ giảng môn Lập trình C/C++ cho sinh viên năm nhất. \
Nhiệm vụ: giải thích lỗi trong bài làm để sinh viên tự sửa được và hiểu khái niệm nằm sau lỗi.

Yêu cầu:
- Viết tiếng Việt, ngắn gọn, thân thiện, xưng "bạn".
- Chỉ ra dòng code liên quan và vì sao nó sai, nối với khái niệm được cung cấp.
- Gợi ý hướng sửa nhưng KHÔNG viết lại lời giải hoàn chỉnh: sinh viên cần tự sửa để học.
- Không bịa thêm thông tin về kết quả chạy ngoài những gì được cung cấp."""

HYBRID_TASK = """Hệ thống luật đã xác định CHÍNH XÁC các lỗi dưới đây. \
Chỉ giải thích những lỗi này, đúng mã lỗi đã cho, không thêm lỗi khác \
(lỗi do luật phát hiện đã được kiểm chứng bằng công cụ, còn lỗi bạn tự đoán thì chưa)."""

# Cách trình bày theo phong cách học (Felder–Silverman rút gọn)
STYLE_GUIDE = {
    "visual": "Sinh viên học tốt qua hình ảnh: mô tả trạng thái bộ nhớ/biến bằng sơ đồ chữ ngắn "
    "(ví dụ: n = ? (rác) ← scanf ghi vào đâu?) hoặc bảng giá trị qua từng bước.",
    "verbal": "Sinh viên học tốt qua lời giải thích: giải thích tuần tự, rõ ràng bằng câu chữ, "
    "nêu quy tắc chung đứng sau lỗi.",
    "active": "Sinh viên học qua thực hành: gợi ý một thử nghiệm cụ thể để tự kiểm chứng "
    "(thêm printf in giá trị, chạy với input nhỏ) thay vì giảng dài.",
    "reflective": "Sinh viên học qua suy ngẫm: đặt một câu hỏi gợi mở để sinh viên tự tìm ra "
    "nguyên nhân trước khi nêu hướng sửa.",
}

LLM_ONLY_TASK = """Hãy tự tìm các lỗi trong bài làm. Với mỗi lỗi, chọn mã gần nhất trong danh mục \
mã lỗi bên dưới và ghi số dòng (0 nếu không xác định được)."""


def _numbered(code: str) -> str:
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(code.splitlines(), 1))


def _group(findings: list[Finding]) -> OrderedDict[str, list[Finding]]:
    groups: OrderedDict[str, list[Finding]] = OrderedDict()
    for f in findings:
        groups.setdefault(f.bug_pattern, []).append(f)
    return groups


class DiagnosisAgent:
    def __init__(self, catalog: Catalog, kg: KnowledgeSource | None = None,
                 llm: FallbackLLM | None = None):  # fmt: skip
        self.catalog = catalog
        self.kg = kg
        self.llm = llm

    # ------------------------------------------------------------ tri thức từ KG

    def _knowledge(self, codes: list[str], styles: list[str], notes: list[str]) -> dict:
        """Khái niệm và hành động sư phạm cho từng mã lỗi; KG tắt thì dùng danh mục YAML."""
        concepts = {c: list(self.catalog.get(c).concepts) for c in codes}
        actions: dict[str, list] = {c: [] for c in codes}
        names: dict[str, str] = {}
        if self.kg is None:
            notes.append(
                "Không kết nối được KG: chỉ dùng danh mục lỗi, không có hành động sư phạm."
            )
            return {"concepts": concepts, "actions": actions, "concept_names": names}
        try:
            for row in self.kg.concepts_for_bugs(codes):
                names[row["id"]] = row["name"]
            for c in codes:
                actions[c] = self.kg.remediation(c, styles, limit=2)
        except Exception as e:  # KG lỗi giữa chừng không được làm hỏng chẩn đoán
            notes.append(f"Lỗi khi truy vấn KG: {e}")
        return {"concepts": concepts, "actions": actions, "concept_names": names}

    # ------------------------------------------------------------ ngữ cảnh chung

    @staticmethod
    def _context(report: SubmissionReport, source: str, problem: ProblemFiles | None) -> str:
        g = report.grading
        parts = []
        if problem is not None:
            parts.append(
                f"## Đề bài {problem.meta.id}: {problem.meta.title}\n{problem.meta.statement}"
            )
        parts.append(f"## Bài làm ({report.language.value})\n```\n{_numbered(source)}\n```")
        res = f"## Kết quả chấm\nVerdict: {g.verdict.value}, đạt {g.passed}/{g.total} test."
        if g.compile_output:
            res += f"\nThông báo biên dịch:\n{g.compile_output[:2000]}"
        sample = g.tests[0] if g.tests else None
        if sample and sample.verdict != Verdict.AC and sample.expected is not None:
            res += (
                f"\nTest mẫu: input={sample.input!r}\nmong đợi={sample.expected!r}\n"
                f"chương trình in ra={sample.stdout!r}"
            )
        parts.append(res)
        return "\n\n".join(parts)

    # ------------------------------------------------------------ chế độ

    def diagnose(
        self,
        report: SubmissionReport,
        source: str,
        problem: ProblemFiles | None = None,
        mode: DiagnosisMode = DiagnosisMode.HYBRID,
        styles: list[str] | None = None,
    ) -> Diagnosis:
        styles = styles or []
        notes: list[str] = []
        if mode == DiagnosisMode.LLM_ONLY:
            return self._llm_only(report, source, problem, notes)
        if mode == DiagnosisMode.HYBRID and self.llm is None:
            notes.append("Chưa cấu hình LLM: trả về giải thích bằng luật.")
            mode = DiagnosisMode.RULE

        groups = _group([f for f in report.findings if not f.suppressed_by])
        for code, rule in dict.fromkeys(
            (f.bug_pattern, f.suppressed_by) for f in report.findings if f.suppressed_by
        ):
            notes.append(f"Bỏ qua cảnh báo {code}: là hệ quả của lỗi gốc khác (luật {rule}).")
        kn = self._knowledge(list(groups), styles, notes)
        if not groups:
            return self._no_findings(report, mode, notes)

        if mode == DiagnosisMode.HYBRID:
            try:
                return self._hybrid(report, source, problem, groups, kn, notes, styles)
            except LLMError as e:
                notes.append(f"LLM không trả lời được ({e}): trả về giải thích bằng luật.")
        return self._rule(report, groups, kn, notes)

    def _items_base(self, groups, kn) -> dict[str, DiagnosisItem]:
        items = {}
        for code, fs in groups.items():
            pattern = self.catalog.get(code)
            acts = kn["actions"][code]
            items[code] = DiagnosisItem(
                bug_pattern=code,
                lines=sorted({f.line for f in fs if f.line}),
                explanation=pattern.hint or pattern.name,
                fix_hint=acts[0].title
                if acts
                else "",  # không có KG: gợi ý đã nằm trong giải thích
                concepts=kn["concepts"][code],
                actions=[a.id for a in acts],
            )
        return items

    def _finish(self, report, items, kn, mode, notes, summary, provider=None, rejected=()):
        concepts = list(dict.fromkeys(c for it in items for c in it.concepts))
        refs = [f"kg:BugPattern:{it.bug_pattern}" for it in items]
        refs += [f"kg:PedagogicalAction:{a}" for it in items for a in it.actions]
        return Diagnosis(
            submission_id=report.submission_id,
            findings=report.findings,
            related_concepts=concepts,
            explanation=summary,
            references=refs,
            items=items,
            mode=mode,
            llm_provider=provider,
            rejected=list(rejected),
            notes=notes,
        )

    def _no_findings(self, report, mode, notes) -> Diagnosis:
        if report.grading.verdict == Verdict.AC:
            summary = "Bài làm đạt mọi test và không phát hiện lỗi nào. Tốt lắm!"
        else:
            summary = (
                f"Bài làm chưa đạt ({report.grading.verdict.value}) nhưng các luật chưa xác định "
                "được nguyên nhân. Hãy so sánh kết quả test mẫu với đầu ra mong đợi."
            )
        return self._finish(report, [], {}, mode, notes, summary)

    def _rule(self, report, groups, kn, notes) -> Diagnosis:
        items = list(self._items_base(groups, kn).values())
        names = ", ".join(self.catalog.get(c).name for c in groups)
        summary = f"Phát hiện {len(items)} loại lỗi: {names}."
        return self._finish(report, items, kn, DiagnosisMode.RULE, notes, summary)

    def _hybrid(self, report, source, problem, groups, kn, notes, styles=()) -> Diagnosis:
        base = self._items_base(groups, kn)
        lines = []
        for code, fs in groups.items():
            p = self.catalog.get(code)
            concepts = ", ".join(kn["concept_names"].get(c, c) for c in kn["concepts"][code])
            acts = "; ".join(f"{a.title}: {a.content}" for a in kn["actions"][code])
            where = ", ".join(f"dòng {f.line}" if f.line else "không rõ dòng" for f in fs)
            msgs = " | ".join(dict.fromkeys(f"[{f.source}] {f.message}" for f in fs))
            lines.append(
                f"- {code} ({p.name}) tại {where}\n  công cụ báo: {msgs}\n"
                f"  khái niệm liên quan: {concepts}\n  gợi ý chuẩn: {p.hint}\n"
                f"  hành động sư phạm trong KG: {acts or '(chưa có)'}"
            )
        guide = "\n".join(f"- {STYLE_GUIDE[s]}" for s in styles if s in STYLE_GUIDE)
        user = (
            f"{self._context(report, source, problem)}\n\n"
            + (f"## Cách trình bày phù hợp với sinh viên này\n{guide}\n\n" if guide else "")
            + f"## Lỗi đã xác định\n{HYBRID_TASK}\n"
            + "\n".join(lines)
        )
        schema = _schema(list(groups), with_line=False)
        res = self.llm.generate(SYSTEM_PROMPT, user, schema)
        notes += [f"Đã lùi sang provider sau vì: {a}" for a in res.attempts]

        rejected = []
        for it in res.data.get("items", []):
            code = it.get("bug_pattern")
            if code not in base:  # LLM bịa mã lỗi -> loại, giữ giải thích của luật
                rejected.append(str(code))
                continue
            base[code].explanation = it.get("explanation") or base[code].explanation
            base[code].fix_hint = it.get("fix_hint") or base[code].fix_hint
        summary = res.data.get("summary") or f"Phát hiện {len(base)} loại lỗi."
        return self._finish(report, list(base.values()), kn, DiagnosisMode.HYBRID, notes,
                            summary, res.provider, rejected)  # fmt: skip

    def _llm_only(self, report, source, problem, notes) -> Diagnosis:
        if self.llm is None:
            raise LLMError("chế độ llm_only cần cấu hình LLM")
        codes = sorted(self.catalog.codes())
        catalog = "\n".join(f"- {c}: {self.catalog.get(c).name}" for c in codes)
        user = (
            f"{self._context(report, source, problem)}\n\n## Nhiệm vụ\n{LLM_ONLY_TASK}\n"
            f"\n## Danh mục mã lỗi\n{catalog}"
        )
        res = self.llm.generate(SYSTEM_PROMPT, user, _schema(codes, with_line=True))
        items, findings, rejected = [], [], []
        for it in res.data.get("items", []):
            code = it.get("bug_pattern")
            if code not in self.catalog:
                rejected.append(str(code))
                continue
            line = it.get("line") or None
            findings.append(Finding(bug_pattern=code, source="llm", line=line,
                                    message=it.get("explanation", ""), confidence=0.5))  # fmt: skip
            items.append(DiagnosisItem(bug_pattern=code, lines=[line] if line else [],
                                       explanation=it.get("explanation", ""),
                                       fix_hint=it.get("fix_hint", "")))  # fmt: skip
        return Diagnosis(
            submission_id=report.submission_id,
            findings=findings,
            explanation=res.data.get("summary", ""),
            items=items,
            mode=DiagnosisMode.LLM_ONLY,
            llm_provider=res.provider,
            rejected=rejected,
            notes=notes + [f"Đã lùi sang provider sau vì: {a}" for a in res.attempts],
        )


def _schema(codes: list[str], with_line: bool) -> dict:
    """JSON schema cho đầu ra LLM; `bug_pattern` bị giới hạn trong danh sách mã cho phép."""
    item = {
        "type": "object",
        "properties": {
            "bug_pattern": {"type": "string", "enum": codes},
            "explanation": {
                "type": "string",
                "description": "Vì sao sai, dòng nào, nối với khái niệm (2-4 câu)",
            },
            "fix_hint": {
                "type": "string",
                "description": "Hướng sửa, không viết lại lời giải hoàn chỉnh (1-2 câu)",
            },
        },
        "required": ["bug_pattern", "explanation", "fix_hint"],
        "additionalProperties": False,
    }
    if with_line:
        item["properties"]["line"] = {"type": "integer"}
        item["required"].append("line")
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Tóm tắt 1-2 câu cho sinh viên"},
            "items": {"type": "array", "items": item},
        },
        "required": ["summary", "items"],
        "additionalProperties": False,
    }
