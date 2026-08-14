"""Attach to an already-open TIA Portal and export hardware → cabinet JSON."""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from . import config_store

logger = logging.getLogger("io-portal")

ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = ROOT / "tools" / "tia-openness-export"
EXE_PATH = TOOL_DIR / "bin" / "Release" / "net48" / "CheckPlc.TiaExport.exe"
AML_DIR = ROOT / "aml"

_LOCK = threading.Lock()
_BUSY = False

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _load_aml_mod():
    path = ROOT / "scripts" / "aml_to_cabinet.py"
    spec = importlib.util.spec_from_file_location("aml_to_cabinet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载转换脚本: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decode(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "gbk", "mbcs"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _tia_public_api() -> Path:
    env = os.environ.get("TIA_PUBLICAPI", "").strip()
    if env:
        return Path(env)
    v21 = Path(r"C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48")
    v20 = Path(r"C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20")
    if (v21 / "Siemens.Engineering.Base.dll").exists():
        return v21
    if (v20 / "Siemens.Engineering.dll").exists():
        return v20
    return v21


def _prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    public = _tia_public_api()
    env["TIA_PUBLICAPI"] = str(public)
    extras = [
        str(public),
        r"C:\Program Files\Siemens\Automation\Portal V21\Bin\PublicAPI",
        r"C:\Program Files\Siemens\Automation\Portal V21\Bin",
        r"C:\Program Files\Siemens\Automation\Portal V20\Bin\PublicAPI",
        r"C:\Program Files\Siemens\Automation\Portal V20\Bin",
    ]
    prefix = os.pathsep.join(p for p in extras if Path(p).exists())
    if prefix:
        env["PATH"] = prefix + os.pathsep + env.get("PATH", "")
    return env


def _run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int = 360) -> tuple[int, str]:
    logger.info("portal export cmd: %s", " ".join(cmd))
    kw: dict[str, Any] = {
        "cwd": str(cwd),
        "env": env,
        "capture_output": True,
        "timeout": timeout,
    }
    if sys.platform == "win32":
        kw["creationflags"] = CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, **kw)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "导出超时（超过 6 分钟）。请确认 Portal 已打开工程且 PLC 离线，然后重试。"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"无法启动导出程序: {exc}") from exc
    text = (_decode(proc.stdout or b"") + "\n" + _decode(proc.stderr or b"")).strip()
    return proc.returncode, text


def _export_aml(aml_path: Path, device: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("从 Portal 导出仅支持 Windows 工程机。")
    AML_DIR.mkdir(parents=True, exist_ok=True)
    env = _prepare_env()
    args = ["--out", str(aml_path)]
    if device:
        args.extend(["--device", device])

    if EXE_PATH.exists():
        code, log = _run([str(EXE_PATH), *args], TOOL_DIR, env)
    else:
        bat = TOOL_DIR / "export.bat"
        if not bat.exists():
            raise RuntimeError(f"未找到导出工具: {bat}")
        code, log = _run(["cmd", "/c", str(bat), *args], TOOL_DIR, env, timeout=420)

    # CAx 对 CM/PZD 等非 IO 设备常报 1 个错误，但 AML 里 IO 地址往往已经写出
    if aml_path.exists() and aml_path.stat().st_size >= 32:
        if code != 0:
            logger.warning("CAx exit=%s but AML exists (%s bytes), continue convert", code, aml_path.stat().st_size)
        return log

    raise RuntimeError(_friendly_fail(log))


def _friendly_fail(log: str) -> str:
    attached = "附加到已运行的 TIA Portal" in (log or "") or "工程:" in (log or "")
    tail = "\n".join((log or "").splitlines()[-16:])
    if "未找到已打开工程" in (log or "") and not attached:
        return (
            "未找到已打开的 Portal 工程。\n"
            "请先用 TIA Portal 打开目标工程，确认 PLC 离线，再点导出。\n\n"
            + tail
        )
    if not attached and "附加失败" in (log or ""):
        return (
            "无法附加到 TIA Portal。\n"
            "请确认：当前 Windows 用户已加入组「Siemens TIA Openness」并重新登录；"
            "用同一个 Windows 账户打开 Portal 和本工具（不要管理员）。\n\n"
            + tail
        )
    low = (log or "").lower()
    if "build failed" in low:
        return (
            "导出工具编译失败。首次使用需安装 .NET SDK，并确认 TIA PublicAPI 路径。\n\n"
            + tail
        )
    if not (log or "").strip():
        return "导出失败（无输出）。请先打开 Portal 工程后重试。"
    return "从 Portal 导出失败：\n" + tail


def export_open_portal(
    name: str,
    ip: str = "",
    device: str = "",
    rack: int = 0,
    slot: int = 1,
    db_config: int = 810,
    db_runtime: int = 811,
) -> dict[str, Any]:
    """Attach to running TIA, export CAx AML, write configs/<name>.json."""
    global _BUSY
    safe = config_store.safe_config_name(name)
    device = (device or "").strip()
    ip = (ip or "").strip()

    with _LOCK:
        if _BUSY:
            raise RuntimeError("正在导出中，请稍候。")
        _BUSY = True
    try:
        aml_path = AML_DIR / f"{safe}.aml"
        log = _export_aml(aml_path, device)

        aml_mod = _load_aml_mod()
        try:
            tree = ET.parse(str(aml_path))
        except ET.ParseError as exc:
            raise RuntimeError(f"导出的 AML 无法解析: {exc}") from exc

        root = tree.getroot()
        modules = aml_mod.extract_modules(root, device=device)
        if not modules:
            raise RuntimeError(
                "未在导出结果中解析到带地址的 IO 模块。\n"
                "请确认工程含 DI/DQ/AI/AQ，且 PLC 离线后重新导出。"
            )

        use_ip = ip or aml_mod.guess_ip(root) or "192.168.0.1"
        cab = aml_mod.modules_to_cabinet(modules, safe, use_ip)
        cab["plc"]["ip"] = use_ip
        cab["plc"]["rack"] = int(rack)
        cab["plc"]["slot"] = int(slot)
        cab["plc"]["db_config"] = int(db_config)
        cab["plc"]["db_runtime"] = int(db_runtime)
        saved = config_store.save_config(safe, cab)
        cab = config_store.load_config(saved)

        project = ""
        m = re.search(r"工程:\s*(.+)", log)
        if m:
            project = m.group(1).strip()

        enabled = config_store.enabled_counts(cab)
        imp = cab.get("_import") or {}
        truncated = imp.get("truncated") or {}
        stations = imp.get("stations") or []
        warnings: list[str] = []
        if re.search(r"错误:\s*[1-9]", log) or re.search(r"errors=\s*[1-9]", log):
            warnings.append(
                "CAx 导出有错误（常见于 CM 通信模块、PZD 报文等非 IO 设备，"
                "一般不影响 DI/DQ/AI/AQ 地址）。请对照 TIA 设备视图核对地址一览。"
            )
        if truncated:
            detail = "、".join(f"{k.upper()} {n} 个" for k, n in truncated.items())
            warnings.append(
                f"解析到 {detail}，每类最多 20 槽已截断。请在「站名」填写当前 PLC/ET200 后再导出。"
            )
        elif len(stations) > 1:
            warnings.append(
                "工程含多个站：" + "、".join(stations) + "。若数量与当前柜子不符，请填写「站名」只导出该站。"
            )
        cax_warning = " ".join(warnings)
        return {
            "ok": True,
            "name": saved,
            "ip": use_ip,
            "project": project,
            "enabled": enabled,
            "modules": len(modules),
            "stations": stations,
            "truncated": truncated,
            "path": str(config_store.config_path(saved)),
            "cabinet": cab,
            "cax_warning": cax_warning,
            "log_tail": "\n".join(log.splitlines()[-8:]),
        }
    finally:
        with _LOCK:
            _BUSY = False
