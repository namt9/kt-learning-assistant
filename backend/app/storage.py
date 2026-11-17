"""Lưu log nộp bài vào SQLite. Bảng `findings` là dữ liệu đầu vào cho khai phá luật (C)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .schemas import SubmissionReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id          TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL,
    problem_id  TEXT NOT NULL,
    language    TEXT NOT NULL,
    source_code TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    score       REAL NOT NULL,
    created_at  TEXT NOT NULL,
    report_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_student ON submissions(student_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sub_problem ON submissions(problem_id);

CREATE TABLE IF NOT EXISTS findings (
    submission_id TEXT NOT NULL REFERENCES submissions(id),
    bug_pattern   TEXT NOT NULL,
    source        TEXT NOT NULL,
    line          INTEGER,
    message       TEXT NOT NULL,
    confidence    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_find_sub ON findings(submission_id);
CREATE INDEX IF NOT EXISTS idx_find_pattern ON findings(bug_pattern);
"""


class Storage:
    def __init__(self, path: Path):
        self.path = path
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save(self, report: SubmissionReport, source_code: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    report.submission_id,
                    report.student_id,
                    report.problem_id,
                    report.language.value,
                    source_code,
                    report.grading.verdict.value,
                    report.grading.score,
                    report.created_at.isoformat(),
                    report.model_dump_json(),
                ),
            )
            c.executemany(
                "INSERT INTO findings VALUES (?,?,?,?,?,?)",
                [
                    (report.submission_id, f.bug_pattern, f.source, f.line, f.message, f.confidence)
                    for f in report.findings
                ],
            )

    def get(self, submission_id: str) -> SubmissionReport | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT report_json FROM submissions WHERE id = ?", (submission_id,)
            ).fetchone()
        return SubmissionReport.model_validate_json(row["report_json"]) if row else None

    def history(self, student_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, problem_id, language, verdict, score, created_at FROM submissions "
                "WHERE student_id = ? ORDER BY created_at DESC LIMIT ?",
                (student_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
