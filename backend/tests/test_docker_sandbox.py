"""Chạy lại các ca chấm với DockerRunner (sandbox thật, có cppcheck).

Tự bỏ qua nếu không có Docker hoặc chưa build image: docker build -t kt-sandbox sandbox/
"""

import shutil
import subprocess

import pytest

from backend.app.config import ROOT
from backend.app.judge.judge import Judge
from backend.app.judge.runner import DockerRunner
from backend.app.schemas import Language, Submission, Verdict

from .conftest import FIXTURES
from .test_judge import CASES

IMAGE = "kt-sandbox"


def _image_ready() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _image_ready(), reason=f"chưa có Docker image {IMAGE}")


@pytest.fixture(scope="module")
def docker_judge(catalog):
    # Docker Desktop chỉ mount được thư mục dưới /home, nên dùng thư mục trong repo
    work = ROOT / ".sandbox_work" / "pytest"
    return Judge(DockerRunner(IMAGE), catalog, work)


def run(judge, problems, pid, src, lang=Language.C):
    sub = Submission(student_id="sv1", problem_id=pid, language=lang, source_code=src)
    return judge.evaluate(sub, problems.get(pid))


def test_tools_inside_image():
    r = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            IMAGE,
            "sh",
            "-c",
            "gcc --version && cppcheck --version && id -un",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "cppcheck" in r.stdout.lower() and "runner" in r.stdout


def test_no_network_in_sandbox(docker_judge):
    # --network none: không có eth0, bảng định tuyến rỗng (chỉ còn dòng tiêu đề).
    # (Không dùng /sys/class/net vì Docker Desktop còn hiện các thiết bị tunnel giả của kernel.)
    r = docker_judge.runner.run(
        ["sh", "-c", "cat /proc/net/route; cut -d: -f1 /proc/net/dev"],
        ROOT / "sandbox",
        timeout_s=10,
    )
    assert r.exit_code == 0, r.stderr
    assert len(r.stdout.splitlines()) > 2 and "eth0" not in r.stdout
    assert not any(line.split()[1:2] == ["00000000"] for line in r.stdout.splitlines())


@pytest.mark.parametrize("problem_dir", sorted((ROOT / "data" / "problems").glob("P*")))
def test_reference_solutions(docker_judge, problems, problem_dir):
    pid = problem_dir.name.split("_")[0]
    rep = run(docker_judge, problems, pid, (problem_dir / "solution.c").read_text())
    assert rep.grading.verdict == Verdict.AC, rep
    assert rep.tools_unavailable == []
    serious = {f.bug_pattern for f in rep.findings} - {"UNUSED_VAR", "UNCLASSIFIED"}
    assert not serious, rep.findings


@pytest.mark.parametrize(("fixture", "pid", "verdict", "expected"), CASES)
def test_buggy_programs(docker_judge, problems, fixture, pid, verdict, expected):
    rep = run(docker_judge, problems, pid, (FIXTURES / fixture).read_text())
    if verdict is not None:
        assert rep.grading.verdict == verdict, rep.grading
    assert expected <= {f.bug_pattern for f in rep.findings}, rep.findings


def test_fork_bomb_is_contained(docker_judge, problems):
    src = "#include <unistd.h>\nint main(void){ while (1) fork(); }"
    rep = run(docker_judge, problems, "P001", src)
    assert rep.grading.verdict in (Verdict.TLE, Verdict.RE)


def test_cppcheck_findings_are_classified(docker_judge, problems):
    rep = run(docker_judge, problems, "P001", (FIXTURES / "uninit.c").read_text())
    from_cppcheck = [f for f in rep.findings if f.source == "cppcheck"]
    assert from_cppcheck, "cppcheck không báo gì: kiểm tra image sandbox"
    assert all(f.bug_pattern != "UNCLASSIFIED" for f in from_cppcheck), from_cppcheck
