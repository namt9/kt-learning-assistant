"""Chạy lệnh trong sandbox.

- DockerRunner: mỗi lệnh chạy trong một container riêng, không mạng, giới hạn RAM/CPU/số tiến trình.
  Đây là chế độ phải dùng khi chạy code của người khác (demo, chấm thật).
- LocalRunner: chạy thẳng trên máy với giới hạn rlimit. KHÔNG an toàn, chỉ dùng khi phát triển/test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

TIMEOUT_EXIT = 124  # giống lệnh `timeout` của coreutils


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    time_ms: int
    timed_out: bool = False
    oom_killed: bool = False


class Runner(Protocol):
    def available_tools(self) -> set[str]: ...

    def run(
        self,
        argv: list[str],
        workdir: Path,
        stdin: str | None = None,
        timeout_s: float = 2.0,
        memory_mb: int | None = 256,
    ) -> ExecResult: ...


def _decode(b: bytes, limit: int) -> str:
    text = b[:limit].decode("utf-8", errors="replace")
    return text + ("\n...[đã cắt bớt]" if len(b) > limit else "")


class LocalRunner:
    def __init__(self, max_output_bytes: int = 1 << 20):
        self.max_output_bytes = max_output_bytes

    def available_tools(self) -> set[str]:
        return {t for t in ("gcc", "g++", "cppcheck") if shutil.which(t)}

    def run(self, argv, workdir, stdin=None, timeout_s=2.0, memory_mb=256) -> ExecResult:
        def limits():  # chạy trong tiến trình con trước exec
            import resource

            cpu = int(timeout_s) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_FSIZE, (16 << 20, 16 << 20))
            if memory_mb:  # AddressSanitizer cần nhiều bộ nhớ ảo nên truyền None khi chạy ASan
                lim = memory_mb << 20
                resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
            os.setsid()

        start = time.monotonic()
        try:
            p = subprocess.run(
                argv,
                cwd=workdir,
                input=(stdin or "").encode(),
                capture_output=True,
                timeout=timeout_s,
                preexec_fn=limits,
            )
        except subprocess.TimeoutExpired as e:
            return ExecResult(
                TIMEOUT_EXIT,
                _decode(e.stdout or b"", self.max_output_bytes),
                _decode(e.stderr or b"", self.max_output_bytes),
                int((time.monotonic() - start) * 1000),
                timed_out=True,
            )
        elapsed = int((time.monotonic() - start) * 1000)
        timed_out = p.returncode == -9 or p.returncode == -24  # SIGKILL / SIGXCPU do RLIMIT_CPU
        return ExecResult(
            TIMEOUT_EXIT if timed_out else p.returncode,
            _decode(p.stdout, self.max_output_bytes),
            _decode(p.stderr, self.max_output_bytes),
            elapsed,
            timed_out=timed_out,
        )


class DockerRunner:
    """Mỗi lệnh = một `docker run --rm`. Thư mục làm việc được mount vào /work."""

    def __init__(self, image: str, max_output_bytes: int = 1 << 20):
        self.image = image
        self.max_output_bytes = max_output_bytes

    def available_tools(self) -> set[str]:
        return {"gcc", "g++", "cppcheck"}  # cài sẵn trong sandbox/Dockerfile

    def check(self) -> None:
        r = subprocess.run(["docker", "image", "inspect", self.image], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(
                f"Không tìm thấy Docker image '{self.image}'. Chạy: docker build -t "
                f"{self.image} sandbox/  (hoặc đặt SANDBOX_MODE=local khi phát triển)"
            )

    def run(self, argv, workdir, stdin=None, timeout_s=2.0, memory_mb=256) -> ExecResult:
        mem = memory_mb or 1024  # ASan: cho nhiều RAM hơn
        cmd = [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--memory", f"{mem + 32}m", "--memory-swap", f"{mem + 32}m",
            "--pids-limit", "64",
            "--cpus", "1",
            "--security-opt", "no-new-privileges",
            "-v", f"{workdir.resolve()}:/work",
            "-w", "/work",
            self.image,
            "timeout", "-s", "KILL", f"{timeout_s}s", *argv,
        ]  # fmt: skip
        start = time.monotonic()
        try:
            p = subprocess.run(
                cmd, input=(stdin or "").encode(), capture_output=True, timeout=timeout_s + 30
            )
        except subprocess.TimeoutExpired:
            return ExecResult(TIMEOUT_EXIT, "", "", int((time.monotonic() - start) * 1000), True)
        elapsed = int((time.monotonic() - start) * 1000)
        # `timeout -s KILL` -> 137; OOM killer cũng -> 137. Phân biệt theo thời gian chạy.
        killed = p.returncode == 137
        timed_out = killed and elapsed >= timeout_s * 1000
        return ExecResult(
            TIMEOUT_EXIT if timed_out else p.returncode,
            _decode(p.stdout, self.max_output_bytes),
            _decode(p.stderr, self.max_output_bytes),
            elapsed,
            timed_out=timed_out,
            oom_killed=killed and not timed_out,
        )


def make_runner(mode: str, image: str, max_output_bytes: int) -> Runner:
    if mode == "local":
        return LocalRunner(max_output_bytes)
    if mode == "docker":
        return DockerRunner(image, max_output_bytes)
    raise ValueError(f"SANDBOX_MODE không hợp lệ: {mode!r} (dùng 'docker' hoặc 'local')")
