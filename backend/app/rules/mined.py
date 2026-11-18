"""Áp luật khai phá (knowledge/mined_rules.yaml) lên kết quả của tầng luật v0.

Chỉ dùng luật khử nhiễu (`kind: suppress`): đánh giá trong docs/mining_report.md cho thấy chúng
tăng F1 trên bài chưa thấy, còn luật bổ sung thì làm giảm. Cảnh báo bị khử KHÔNG bị xoá, chỉ được
gắn `suppressed_by`, để giao diện và báo cáo vẫn truy vết được vì sao nó bị bỏ qua.

Hệ v0 không gọi module này, để còn làm mốc so sánh v0 và v1.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..schemas import Finding, SubmissionReport


class MinedRules:
    def __init__(self, rules: list[dict], min_confidence: float = 0.8,
                 kinds: tuple[str, ...] = ("suppress",)):  # fmt: skip
        self.rules = [r for r in rules if r["kind"] in kinds and r["confidence"] >= min_confidence]

    @classmethod
    def load(cls, path: Path, **kw) -> MinedRules:
        if not path.exists():
            return cls([], **kw)
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")).get("rules", []), **kw)

    def __len__(self) -> int:
        return len(self.rules)

    def apply(self, report: SubmissionReport, source: str) -> list[Finding]:
        """Trả về danh sách finding mới, cảnh báo hệ quả được gắn `suppressed_by`."""
        from ..mining.mine import transaction  # dùng đúng cách dựng giao dịch như lúc khai phá

        rec = {
            "verdict": report.grading.verdict.value,
            "findings": [{"bug_pattern": f.bug_pattern} for f in report.findings],
            "source": source,
        }
        items = transaction(rec, with_labels=False)
        suppressed: dict[str, str] = {}
        for r in self.rules:
            if r["then"] not in suppressed and set(r["if"]) <= items:
                suppressed[r["then"]] = r["id"]
        codes = {f.bug_pattern for f in report.findings}
        if codes and codes <= set(suppressed):  # không bao giờ khử hết: phải còn lỗi gốc
            return list(report.findings)
        return [
            f.model_copy(update={"suppressed_by": suppressed.get(f.bug_pattern)})
            for f in report.findings
        ]
