"""Load / save cabinet JSON configs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"


def list_configs() -> list[str]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in CONFIG_DIR.glob("*.json"))


def load_config(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(name: str, data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_default() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    names = list_configs()
    if names:
        return "example_cabinet" if "example_cabinet" in names else names[0]
    # should already exist from repo
    return "example_cabinet"
