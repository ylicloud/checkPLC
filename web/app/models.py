from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    ip: str = "192.168.0.1"
    rack: int = 0
    slot: int = 1
    mock: bool = False
    db_config: int = 10
    db_runtime: int = 11


class DqSetRequest(BaseModel):
    slot: int = Field(ge=1, le=20)
    channel: int = Field(ge=1, le=32, description="1-based channel in slot")
    value: bool = True


class DqResetRequest(BaseModel):
    slot: Optional[int] = Field(default=None, ge=1, le=20)


class SaveConfigRequest(BaseModel):
    name: str
    cabinet: dict[str, Any]
    push_to_plc: bool = True


class MockDiRequest(BaseModel):
    start_addr: int
    bit: int = Field(ge=0, le=7)
    value: bool = True


class MockAiRequest(BaseModel):
    start_addr: int
    raw: int = 5530  # ~4mA on 0-20mA/27648
