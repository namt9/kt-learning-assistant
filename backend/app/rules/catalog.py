"""Đọc danh mục Bug Pattern (knowledge/bug_patterns.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BugPattern:
    code: str
    name: str
    concepts: tuple[str, ...]
    hint: str


class Catalog:
    def __init__(self, path: Path):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))["bug_patterns"]
        self._items = {
            p["code"]: BugPattern(p["code"], p["name"], tuple(p["concepts"]), p.get("hint", ""))
            for p in raw
        }

    def __contains__(self, code: str) -> bool:
        return code in self._items

    def get(self, code: str) -> BugPattern:
        return self._items.get(code) or self._items["UNCLASSIFIED"]

    def codes(self) -> set[str]:
        return set(self._items)
