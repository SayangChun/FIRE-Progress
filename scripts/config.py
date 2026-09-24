"""配置加载与路径常量。

约定：代码中不出现任何硬编码的业务口径，全部来自 config.yaml。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
FIXTURES_DIR = ROOT / "tests" / "fixtures"

LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.json"


class Config(dict):
    """让配置支持 cfg.fire.monthly_expense 这样的点号访问。"""

    def __getattr__(self, item: str) -> Any:
        try:
            value = self[item]
        except KeyError as exc:  # pragma: no cover - 配置写错时给出清晰报错
            raise AttributeError(f"配置项不存在: {item}") from exc
        return Config(value) if isinstance(value, dict) else value


def load(path: str | Path | None = None) -> Config:
    path = Path(path) if path else CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(data)


def env(name: str, default: str | None = None) -> str | None:
    """读取环境变量，空字符串视为未设置。"""
    value = os.environ.get(name)
    return value if value not in (None, "") else default
