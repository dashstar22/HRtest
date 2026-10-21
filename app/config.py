"""运行时配置：优先读环境变量，其次读项目根目录的 .env 文件。"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _load_env_file() -> None:
    """极简 .env 解析，避免为 Demo 引入 python-dotenv 依赖。"""
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "3"))

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "hr_screening.db"))
SAMPLES_DIR = BASE_DIR / "samples"
STATIC_DIR = BASE_DIR / "static"

# 没有配置 Key 时自动降级为规则引擎，保证 Demo 在任何环境下都能跑通。
AI_MODE = "deepseek" if DEEPSEEK_API_KEY else "rule"
