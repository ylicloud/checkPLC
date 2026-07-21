"""DB10 / DB11 fixed offsets matching S7 non-optimized UDT layout.

UDT_DigSlot (Standard): Bool@0.0 + pad + UInt@2 + USInt@4 + USInt@5 = 6 bytes
UDT_AnaSlot (Standard): ... + Int@6 + Real@8 + Real@12 = 16 bytes
"""

from __future__ import annotations

import struct
from typing import Any

DIG_SLOT_SIZE = 6
ANA_SLOT_SIZE = 16
SLOTS = 20

DI_OFFSET = 0                      # 20 * 6 = 120
DQ_OFFSET = DI_OFFSET + SLOTS * DIG_SLOT_SIZE  # 120
AI_OFFSET = DQ_OFFSET + SLOTS * DIG_SLOT_SIZE  # 240
AQ_OFFSET = AI_OFFSET + SLOTS * ANA_SLOT_SIZE  # 560
CONFIG_DB_SIZE = AQ_OFFSET + SLOTS * ANA_SLOT_SIZE  # 880

DQ_FORCE_OFFSET = 0
AQ_MA_OFFSET = 80
HEARTBEAT_OFFSET = 720
RUNTIME_DB_SIZE = 724


def _u16_be(value: int) -> bytes:
    return struct.pack(">H", value & 0xFFFF)


def _i16_be(value: int) -> bytes:
    return struct.pack(">h", int(value))


def _f32_be(value: float) -> bytes:
    return struct.pack(">f", float(value))


def pack_dig_slot(enable: bool, start_addr: int, channel_count: int) -> bytes:
    # 6 bytes — 与 TIA Standard UDT_DigSlot 步长一致
    return bytes(
        [
            1 if enable else 0,  # byte0 bit0 = Enable
            0,  # 对齐填充
            *_u16_be(start_addr),
            channel_count & 0xFF,  # ChannelCount USInt
            0,  # Reserved USInt
        ]
    )


def pack_ana_slot(
    enable: bool,
    start_addr: int,
    channel_count: int,
    raw_full: int = 27648,
    eng_full_ma: float = 20.0,
    eng_min_ma: float = 4.0,
) -> bytes:
    return bytes(
        [
            1 if enable else 0,
            0,
            *_u16_be(start_addr),
            channel_count & 0xFF,
            0,
            *_i16_be(raw_full),
            *_f32_be(eng_full_ma),
            *_f32_be(eng_min_ma),
        ]
    )


def pack_config_db(cabinet: dict[str, Any]) -> bytearray:
    buf = bytearray(CONFIG_DB_SIZE)

    def write_dig(section: str, base: int) -> None:
        slots = {s["slot"]: s for s in cabinet.get(section, [])}
        for i in range(1, SLOTS + 1):
            s = slots.get(i, {})
            raw = pack_dig_slot(
                bool(s.get("enable", False)),
                int(s.get("start_addr", 0)),
                int(s.get("channel_count", 16)),
            )
            off = base + (i - 1) * DIG_SLOT_SIZE
            buf[off : off + DIG_SLOT_SIZE] = raw

    def write_ana(section: str, base: int) -> None:
        slots = {s["slot"]: s for s in cabinet.get(section, [])}
        for i in range(1, SLOTS + 1):
            s = slots.get(i, {})
            raw = pack_ana_slot(
                bool(s.get("enable", False)),
                int(s.get("start_addr", 0)),
                int(s.get("channel_count", 8)),
                int(s.get("raw_full", 27648)),
                float(s.get("eng_full_ma", 20.0)),
                float(s.get("eng_min_ma", 4.0)),
            )
            off = base + (i - 1) * ANA_SLOT_SIZE
            buf[off : off + ANA_SLOT_SIZE] = raw

    write_dig("di", DI_OFFSET)
    write_dig("dq", DQ_OFFSET)
    write_ana("ai", AI_OFFSET)
    write_ana("aq", AQ_OFFSET)
    return buf


def pack_dq_force(slot_bits: list[int]) -> bytearray:
    """slot_bits: length 20, each uint32 bitmask bit0=ch1. S7 big-endian DWORD."""
    buf = bytearray(80)
    for i in range(20):
        val = slot_bits[i] if i < len(slot_bits) else 0
        buf[i * 4 : (i + 1) * 4] = struct.pack(">I", val & 0xFFFFFFFF)
    return buf


def unpack_dq_force(data: bytes) -> list[int]:
    out: list[int] = []
    for i in range(20):
        off = i * 4
        if off + 4 > len(data):
            out.append(0)
            continue
        out.append(int(struct.unpack(">I", data[off : off + 4])[0]))
    return out


def unpack_aq_ma(data: bytes, count: int = 160) -> list[float]:
    out: list[float] = []
    for i in range(count):
        off = AQ_MA_OFFSET + i * 4
        if off + 4 > len(data):
            break
        out.append(struct.unpack(">f", data[off : off + 4])[0])
    return out


def enabled_slots(cabinet: dict[str, Any], section: str) -> list[dict[str, Any]]:
    return [s for s in cabinet.get(section, []) if s.get("enable")]


def global_channel_map(cabinet: dict[str, Any], section: str) -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    g = 0
    for s in sorted(cabinet.get(section, []), key=lambda x: x["slot"]):
        if not s.get("enable"):
            continue
        n = int(s.get("channel_count", 0))
        for ch in range(n):
            g += 1
            result.append((g, int(s["slot"]), ch))
    return result
