"""Nạp ngân hàng bài tập từ data/problems/<thư mục bài>/."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .schemas import Language, Problem, ProblemSummary


@dataclass(frozen=True)
class TestCase:
    id: str
    input: str
    expected: str


@dataclass(frozen=True)
class ProblemData:
    meta: Problem
    tests: list[TestCase]


class ProblemNotFound(KeyError):
    pass


class ProblemRepository:
    def __init__(self, root: Path):
        self.root = root
        self._cache: dict[str, ProblemData] = {}
        self.reload()

    def reload(self) -> None:
        self._cache = {}
        for d in sorted(p for p in self.root.iterdir() if (p / "problem.yaml").is_file()):
            data = _load_problem(d)
            self._cache[data.meta.id] = data

    def list(self) -> list[ProblemSummary]:
        return [ProblemSummary(**d.meta.model_dump()) for d in self._cache.values()]

    def get(self, problem_id: str) -> ProblemData:
        try:
            return self._cache[problem_id]
        except KeyError:
            raise ProblemNotFound(problem_id) from None


def _test_sort_key(p: Path):
    return (0, int(p.stem)) if p.stem.isdigit() else (1, p.stem)


def _load_problem(d: Path) -> ProblemData:
    meta = yaml.safe_load((d / "problem.yaml").read_text(encoding="utf-8"))
    statement_file = d / "statement.md"
    statement = statement_file.read_text(encoding="utf-8") if statement_file.exists() else ""
    tests = [
        TestCase(
            id=f.stem,
            input=f.read_text(encoding="utf-8"),
            expected=f.with_suffix(".out").read_text(encoding="utf-8"),
        )
        for f in sorted((d / "tests").glob("*.in"), key=_test_sort_key)
        if f.with_suffix(".out").exists()
    ]
    problem = Problem(
        id=str(meta["id"]),
        title=meta["title"],
        concepts=meta.get("concepts", []),
        statement=statement,
        languages=[Language(x) for x in meta.get("language", ["c", "cpp"])],
        time_limit_s=float(meta.get("time_limit_s", 1)),
        memory_mb=int(meta.get("memory_mb", 64)),
        test_count=len(tests),
    )
    return ProblemData(meta=problem, tests=tests)
