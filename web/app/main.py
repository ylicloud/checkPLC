from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
def configs() -> dict:
    return {"items": config_store.list_configs()}


@app.get("/api/configs/{name}")
def get_config(name: str) -> dict:
    try:
        return config_store.load_config(name)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/configs")
def save_config(body: SaveConfigRequest) -> dict:
    config_store.save_config(body.name, body.cabinet)
    scanner.set_cabinet(body.cabinet)
    plc = body.cabinet.get("plc", {})
    bridge.db_config = int(plc.get("db_config", 10))
    bridge.db_runtime = int(plc.get("db_runtime", 11))
    pushed = False
    if body.push_to_plc and bridge.connected:
        scanner.push_config_to_plc()
        pushed = True
    return {"ok": True, "pushed": pushed}


@app.post("/api/connect")
def connect(body: ConnectRequest) -> dict:
    try:
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
    bridge.disconnect()
    return {"ok": True, "connected": False}


@app.get("/api/snapshot")
def snapshot() -> dict:
    events = [
        {
            "kind": e.kind,
            "channel": e.channel,
            "text": e.text,
            "ma": e.ma,
            "ts": e.ts,
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
    return {"ok": True}


@app.post("/api/mock/ai")
def mock_ai(body: MockAiRequest) -> dict:
    if not bridge.mock:
        raise HTTPException(400, "仅 mock 模式可用")
    bridge.mock_set_ai_raw(body.start_addr, body.raw)
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
