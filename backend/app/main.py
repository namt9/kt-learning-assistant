"""API hệ nền v0: bài tập, nộp bài, kết quả chấm, lịch sử nộp."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .config import load_settings
from .judge.judge import Judge
from .judge.runner import DockerRunner, make_runner
from .problems import ProblemNotFound, ProblemRepository
from .rules.catalog import Catalog
from .schemas import LearningPath, Problem, ProblemSummary, Submission, SubmissionReport
from .storage import Storage

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
UI_FILE = FRONTEND / "v0" / "index.html"
KG_VIEWER_FILE = FRONTEND / "kg" / "index.html"


def build_app(settings=None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runner = make_runner(
            settings.sandbox_mode, settings.sandbox_image, settings.max_output_bytes
        )
        if isinstance(runner, DockerRunner):
            runner.check()
        app.state.problems = ProblemRepository(settings.problems_dir)
        app.state.storage = Storage(settings.db_path)
        app.state.judge = Judge(
            runner, Catalog(settings.bug_patterns_file), settings.work_dir,
            settings.compile_timeout_s,
        )  # fmt: skip
        app.state.sandbox_mode = settings.sandbox_mode
        app.state.kg = None
        yield
        if app.state.kg is not None:
            app.state.kg.driver.close()

    app = FastAPI(title="Trợ lý học tập thông minh: hệ nền v0", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "sandbox": app.state.sandbox_mode}

    @app.get("/", include_in_schema=False)
    def ui():
        return FileResponse(UI_FILE)

    @app.get("/problems", response_model=list[ProblemSummary])
    def list_problems():
        return app.state.problems.list()

    @app.get("/problems/{problem_id}", response_model=Problem)
    def get_problem(problem_id: str):
        try:
            return app.state.problems.get(problem_id).meta
        except ProblemNotFound:
            raise HTTPException(404, f"Không có bài {problem_id}") from None

    @app.post("/submit", response_model=SubmissionReport)
    def submit(sub: Submission):  # hàm đồng bộ -> FastAPI chạy trong threadpool
        try:
            problem = app.state.problems.get(sub.problem_id)
        except ProblemNotFound:
            raise HTTPException(404, f"Không có bài {sub.problem_id}") from None
        if sub.language not in problem.meta.languages:
            raise HTTPException(400, f"Bài {sub.problem_id} không nhận ngôn ngữ {sub.language}")
        report = app.state.judge.evaluate(sub, problem)
        app.state.storage.save(report, sub.source_code)
        return report

    @app.get("/submissions/{submission_id}", response_model=SubmissionReport)
    def get_submission(submission_id: str):
        report = app.state.storage.get(submission_id)
        if report is None:
            raise HTTPException(404, "Không tìm thấy lần nộp")
        return report

    @app.get("/students/{student_id}/submissions")
    def student_history(student_id: str):
        return app.state.storage.history(student_id)

    # ------------------------------------------------------------ Knowledge Graph (v1)

    def kg():
        """Kết nối Neo4j khi cần; API v0 vẫn chạy được khi Neo4j chưa bật."""
        if getattr(app.state, "kg", None) is None:
            from .kg.queries import KGQueries, connect

            try:
                driver = connect()
                driver.verify_connectivity()
            except Exception as e:
                raise HTTPException(503, f"Không kết nối được Neo4j: {e}") from None
            app.state.kg = KGQueries(driver)
        return app.state.kg

    @app.get("/kg-viewer", include_in_schema=False)
    def kg_viewer():
        return FileResponse(KG_VIEWER_FILE)

    @app.get("/kg/graph")
    def kg_graph(include_students: bool = False):
        return kg().graph(include_students)

    @app.get("/kg/nodes/{node_id}")
    def kg_node(node_id: str):
        node = kg().node(node_id)
        if node is None:
            raise HTTPException(404, f"Không có node {node_id} trong KG")
        return node

    @app.get("/kg/bugs/{code}/remediation")
    def kg_remediation(
        code: str, styles: Annotated[list[str] | None, Query()] = None, limit: int = 3
    ):
        return kg().remediation(code, styles or [], limit)

    @app.get("/kg/students/{student_id}/weak-concepts")
    def kg_weak_concepts(student_id: str, limit: int = 10):
        return kg().student_weak_concepts(student_id, limit)

    @app.get("/kg/students/{student_id}/learning-path", response_model=LearningPath)
    def kg_learning_path(
        student_id: str,
        bugs: Annotated[list[str] | None, Query()] = None,
        styles: Annotated[list[str] | None, Query()] = None,
        max_steps: int = 6,
    ):
        return kg().learning_path(student_id, bugs or [], styles or [], max_steps)

    return app


app = build_app()
