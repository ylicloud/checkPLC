"""Load / save cabinet JSON configs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_config_name(name: str) -> str:
    """Sanitize config name used as filename stem."""
    raw = (name or "").strip()
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = _INVALID.sub("_", raw).rstrip(". ")
    if not raw or raw in {".", ".."}:
        raise ValueError("配置名无效")
    return raw


def list_configs() -> list[str]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in CONFIG_DIR.glob("*.json"))


def load_config(name: str) -> dict[str, Any]:
    safe = safe_config_name(name)
    path = CONFIG_DIR / f"{safe}.json"
    if not path.exists():
        raise FileNotFoundError(safe)
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(name: str, data: dict[str, Any]) -> str:
    """Save cabinet JSON; returns sanitized name actually used."""
    import copy

    safe = safe_config_name(name)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(data or {})
    payload.pop("_meta", None)
    payload["name"] = safe
    # 规范化 enable 为真正的 bool，避免字符串/数字导致前端统计异常
    for kind in ("di", "dq", "ai", "aq"):
        for slot in payload.get(kind, []) or []:
            if isinstance(slot, dict) and "enable" in slot:
                slot["enable"] = bool(slot.get("enable"))
    path = CONFIG_DIR / f"{safe}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        try:
            import os

            os.fsync(f.fileno())
        except OSError:
            pass
    return safe


def config_path(name: str) -> Path:
    return CONFIG_DIR / f"{safe_config_name(name)}.json"


def enabled_counts(data: dict[str, Any]) -> dict[str, int]:
    return {
        k: sum(1 for s in (data.get(k) or []) if s.get("enable"))
        for k in ("di", "dq", "ai", "aq")
    }


def ensure_default() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    names = list_configs()
    if names:
        return "example_cabinet" if "example_cabinet" in names else names[0]
    return "example_cabinet"
