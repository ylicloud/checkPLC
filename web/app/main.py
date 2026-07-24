from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config_store
from .models import (
    ConnectRequest,
    DqResetRequest,
    DqSetRequest,
    MockAiRequest,
    MockDiRequest,
    SaveConfigRequest,
)
from .s7_client import HAS_SNAP7, bridge
from .scanner import scanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("io-portal")

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

app = FastAPI(title="PLC IO 通检 Portal", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    name = config_store.ensure_default()
    try:
        cab = config_store.load_config(name)
        scanner.set_cabinet(cab)
    except Exception as exc:  # noqa: BLE001
        logger.warning("load default config failed: %s", exc)
    scanner.start()


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "snap7": HAS_SNAP7,
        "connected": bridge.connected,
        "mock": bridge.mock,
    }


@app.get("/api/configs")
def configs() -> JSONResponse:
    items = config_store.list_configs()
    return JSONResponse(
        content={
            "items": items,
            "count": len(items),
            "dir": str(config_store.CONFIG_DIR.resolve()),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/configs/{name}")
def get_config(name: str) -> dict:
    try:
        cab = config_store.load_config(name)
        return {
            **cab,
            "_meta": {
                "name": config_store.safe_config_name(name),
                "path": str(config_store.config_path(name)),
                "enabled": config_store.enabled_counts(cab),
            },
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/configs")
def save_config(body: SaveConfigRequest) -> dict:
    try:
        safe = config_store.safe_config_name(body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    cab = body.cabinet
    if body.persist:
        try:
            saved_name = config_store.save_config(body.name, body.cabinet)
            cab = config_store.load_config(saved_name)
            safe = saved_name
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    else:
        # 仅更新内存，不改磁盘（避免「连接」时用旧状态覆盖已保存配置）
        cab = dict(body.cabinet or {})
        cab["name"] = safe

    scanner.set_cabinet(cab)
    plc = cab.get("plc", {})
    bridge.db_config = int(plc.get("db_config", 10))
    bridge.db_runtime = int(plc.get("db_runtime", 11))
    pushed = False
    if body.push_to_plc and bridge.connected:
        scanner.push_config_to_plc()
        pushed = True
    enabled = config_store.enabled_counts(cab)
    return {
        "ok": True,
        "pushed": pushed,
        "persisted": bool(body.persist),
        "name": safe,
        "cabinet": cab,
        "enabled": enabled,
        "path": str(config_store.config_path(safe)),
    }


@app.post("/api/connect")
def connect(body: ConnectRequest) -> dict:
    try:
        scanner.reset_announce_state()
        bridge.db_config = body.db_config
        bridge.db_runtime = body.db_runtime
        bridge.connect(body.ip, body.rack, body.slot, mock=body.mock)
        db_info = {}
        if bridge.connected and not bridge.mock:
            db_info = {
                "db_config_size": bridge.get_db_size(bridge.db_config),
                "db_runtime_size": bridge.get_db_size(bridge.db_runtime),
            }
        if scanner.get_cabinet():
            scanner.push_config_to_plc()
        return {
            "ok": True,
            "connected": True,
            "mock": bridge.mock,
            "snap7": HAS_SNAP7,
            **db_info,
            "config_error": scanner.snapshot().get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"连接失败: {exc}") from exc


@app.post("/api/disconnect")
def disconnect() -> dict:
    # 仍连接时先清 Force，再断开（否则写不进 PLC）
    try:
        if bridge.connected:
            scanner.reset_dq(None)
    except Exception:  # noqa: BLE001
        pass
    scanner.reset_announce_state()
    bridge.disconnect()
    return {"ok": True, "connected": False}


@app.post("/api/events/clear")
def clear_events() -> dict:
    n = scanner.clear_events()
    return {"ok": True, "cleared": n}


@app.get("/api/snapshot")
def snapshot() -> dict:
    events = [
        {
            "kind": e.kind,
            "channel": e.channel,
            "text": e.text,
            "ma": e.ma,
            "ts": e.ts,
            "module_name": e.module_name,
            "module_index": e.module_index,
            "module_count": e.module_count,
        }
        for e in scanner.pop_events()
    ]
    snap = scanner.snapshot()
    snap["events"] = events
    return snap


@app.post("/api/dq/set")
def dq_set(body: DqSetRequest) -> dict:
    if not bridge.connected:
        raise HTTPException(400, "未连接 PLC")
    scanner.set_dq_bit(body.slot, body.channel - 1, body.value)
    return {"ok": True, "dq_force": scanner.snapshot()["dq_force"]}


@app.post("/api/dq/reset")
def dq_reset(body: DqResetRequest) -> dict:
    if not bridge.connected:
        raise HTTPException(400, "未连接 PLC")
    scanner.reset_dq(body.slot)
    return {"ok": True, "dq_force": scanner.snapshot()["dq_force"]}


@app.post("/api/mock/di")
def mock_di(body: MockDiRequest) -> dict:
    if not bridge.mock:
        raise HTTPException(400, "仅 mock 模式可用")
    bridge.mock_set_di_bit(body.start_addr, body.bit, body.value)
    scanner.note_mock_di(body.start_addr, body.bit, body.value)
    info = None
    if body.value:
        info = scanner.inject_di_rising(body.start_addr, body.bit)
    return {
        "ok": True,
        "channel": info["channel"] if info else None,
        "module_name": info.get("module_name") if info else None,
        "module_index": info.get("module_index") if info else None,
        "module_count": info.get("module_count") if info else None,
    }


@app.post("/api/mock/ai")
def mock_ai(body: MockAiRequest) -> dict:
    if not bridge.mock:
        raise HTTPException(400, "仅 mock 模式可用")
    bridge.mock_set_ai_raw(body.start_addr, body.raw)
    info = scanner.inject_ai_change(body.start_addr, body.raw)
    return {
        "ok": True,
        "channel": info["channel"] if info else None,
        "ma": info["ma"] if info else None,
        "module_name": info.get("module_name") if info else None,
        "module_index": info.get("module_index") if info else None,
        "module_count": info.get("module_count") if info else None,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        FRONTEND / "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
