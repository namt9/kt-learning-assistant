"""Bảo đảm danh mục Bug Pattern hợp lệ, vì luật v0, KG và schemas đều dùng chung mã này."""

from pathlib import Path

import yaml

CATALOG = Path(__file__).resolve().parents[2] / "knowledge" / "bug_patterns.yaml"


def test_bug_pattern_codes_unique_and_complete():
    patterns = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["bug_patterns"]
    codes = [p["code"] for p in patterns]
    assert len(codes) == len(set(codes))
    for p in patterns:
        assert {"code", "name", "concepts", "detected_by"} <= p.keys()
