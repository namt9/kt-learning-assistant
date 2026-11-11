"""Cấu hình đọc từ biến môi trường (file .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    problems_dir: Path
    bug_patterns_file: Path
    db_path: Path
    work_dir: Path  # thư mục tạm cho mỗi lần nộp (Docker Desktop chỉ mount được dưới /home)
    sandbox_mode: str  # "docker" (an toàn, dùng khi demo) | "local" (chỉ để phát triển)
    sandbox_image: str
    compile_timeout_s: float
    max_output_bytes: int


def load_settings() -> Settings:
    return Settings(
        problems_dir=Path(os.getenv("PROBLEMS_DIR", ROOT / "data" / "problems")),
        bug_patterns_file=Path(
            os.getenv("BUG_PATTERNS_FILE", ROOT / "knowledge" / "bug_patterns.yaml")
        ),
        db_path=Path(os.getenv("DB_PATH", ROOT / "app.db")),
        work_dir=Path(os.getenv("WORK_DIR", ROOT / ".sandbox_work")),
        sandbox_mode=os.getenv("SANDBOX_MODE", "docker"),
        sandbox_image=os.getenv("SANDBOX_IMAGE", "kt-sandbox"),
        compile_timeout_s=float(os.getenv("COMPILE_TIMEOUT_S", "20")),
        max_output_bytes=int(os.getenv("MAX_OUTPUT_BYTES", str(1 << 20))),
    )
