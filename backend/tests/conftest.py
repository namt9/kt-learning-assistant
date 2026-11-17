from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import ROOT, Settings
from backend.app.judge.judge import Judge
from backend.app.judge.runner import LocalRunner
from backend.app.main import build_app
from backend.app.problems import ProblemRepository
from backend.app.rules.catalog import Catalog

FIXTURES = Path(__file__).parent / "fixtures" / "buggy"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog(ROOT / "knowledge" / "bug_patterns.yaml")


@pytest.fixture(scope="session")
def problems() -> ProblemRepository:
    return ProblemRepository(ROOT / "data" / "problems")


@pytest.fixture(scope="session")
def judge(catalog, tmp_path_factory) -> Judge:
    # LocalRunner: chỉ dùng trong test/phát triển, không an toàn với code lạ
    return Judge(LocalRunner(), catalog, tmp_path_factory.mktemp("work"))


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(
        problems_dir=ROOT / "data" / "problems",
        bug_patterns_file=ROOT / "knowledge" / "bug_patterns.yaml",
        db_path=tmp_path / "test.db",
        work_dir=tmp_path / "work",
        sandbox_mode="local",
        sandbox_image="unused",
        compile_timeout_s=20,
        max_output_bytes=1 << 20,
    )
    with TestClient(build_app(settings)) as c:
        yield c
