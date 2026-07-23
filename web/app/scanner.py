"""DI rising-edge / AI change scanner."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

from . import db_layout
from .s7_client import bridge


@dataclass
class AnnounceEvent:
    kind: str  # di | ai
    channel: int
    text: str
    ma: Optional[float] = None
    ts: float = field(default_factory=time.time)


class IoScanner:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cabinet: dict[str, Any] = {}
        self._prev_di: dict[tuple[int, int], bool] = {}
        self._prev_ai: dict[int, float] = {}
        self._queue: Deque[AnnounceEvent] = deque()
        self._active_di: Optional[int] = None
        self._active_ai: Optional[tuple[int, float]] = None
        self._di_states: dict[int, bool] = {}
        self._ai_values: dict[int, float] = {}
        self._aq_values: list[float] = []
        self._dq_force: list[int] = [0] * 20
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[str] = None
        self._ai_last_announce_ts: float = 0.0
        # 每通道已播报/已测过的毫安整数值：回到原值 A 不再播报
        self._ai_seen_ma: dict[int, set[int]] = {}

    def set_cabinet(self, cabinet: dict[str, Any]) -> None:
        with self._lock:
            self._cabinet = cabinet
            self._prev_di.clear()
            self._prev_ai.clear()
            self._ai_last_announce_ts = 0.0
            self._ai_seen_ma.clear()

    def get_cabinet(self) -> dict[str, Any]:
        with self._lock:
            return self._cabinet

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="io-scanner", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def pop_events(self, max_n: int = 20) -> list[AnnounceEvent]:
        """取出播报事件；只保留最新一条，加快响应（新覆盖旧）。"""
        with self._lock:
            if not self._queue:
                return []
            latest = self._queue[-1]
            self._queue.clear()
            return [latest]

    def clear_events(self) -> int:
        """丢弃未播报事件（页面刷新 / 重新连接时避免连播旧队列）。"""
        with self._lock:
            n = len(self._queue)
            self._queue.clear()
            return n

    def reset_announce_state(self) -> None:
        """连接或刷新时重置播报相关状态。"""
        with self._lock:
            self._queue.clear()
            self._active_di = None
            self._active_ai = None
            self._prev_di.clear()
            self._prev_ai.clear()
            self._ai_last_announce_ts = 0.0
            self._ai_seen_ma.clear()

    def _mark_ai_seen(self, global_ch: int, *ma_vals: float) -> None:
        bucket = self._ai_seen_ma.setdefault(global_ch, set())
        for v in ma_vals:
            if v is None:
                continue
            bucket.add(self._ma_announce_key(v))

    @staticmethod
    def _ma_announce_key(ma: float) -> int:
        """播报去重键：0..24 用整毫安；>24 统一为 25（超出）。"""
        n = int(round(float(ma)))
        if n < 0:
            return 0
        if n > 24:
            return 25
        return n

    def _push_event(self, ev: AnnounceEvent) -> None:
        """新播报覆盖旧播报，不排队。"""
        self._queue.clear()
        self._queue.append(ev)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            dq_q_masks = [0] * 20
            if bridge.connected and self._cabinet:
                try:
                    dq_q_masks = self._dq_q_masks(self._cabinet)
                except Exception:  # noqa: BLE001
                    dq_q_masks = [0] * 20
            return {
                "active_di": self._active_di,
                "active_ai": (
                    {"channel": self._active_ai[0], "ma": self._active_ai[1]}
                    if self._active_ai
                    else None
                ),
                "di_states": dict(self._di_states),
                "ai_values": {str(k): v for k, v in self._ai_values.items()},
                "aq_values": list(self._aq_values),
                "dq_force": list(self._dq_force),
                "dq_q_masks": dq_q_masks,
                "queue_len": len(self._queue),
                "error": self._error,
                "connected": bool(bridge.connected),
                "mock": bool(bridge.mock),
            }

    def set_dq_bit(self, slot: int, channel_index0: int, value: bool) -> None:
        with self._lock:
            if not (1 <= slot <= 20):
                raise ValueError("slot 1..20")
            mask = 1 << channel_index0
            if value:
                self._dq_force[slot - 1] |= mask
            else:
                self._dq_force[slot - 1] &= ~mask
            self._write_dq_force()

    def reset_dq(self, slot: Optional[int] = None) -> None:
        with self._lock:
            if slot is None:
                self._dq_force = [0] * 20
            else:
                self._dq_force[slot - 1] = 0
            self._write_dq_force()

    def push_config_to_plc(self) -> None:
        with self._lock:
            data = db_layout.pack_config_db(self._cabinet)
            bridge.db_config = int(self._cabinet.get("plc", {}).get("db_config", 10))
            bridge.db_runtime = int(self._cabinet.get("plc", {}).get("db_runtime", 11))
            size10 = bridge.get_db_size(bridge.db_config)
            size11 = bridge.get_db_size(bridge.db_runtime)
            try:
                bridge.db_write(bridge.db_config, 0, data)
                # 仅写配置，不要用可能错误的回读覆盖本地 Force，再写回把 PLC 清掉
                self._write_dq_force()
                self._error = None
            except Exception as exc:  # noqa: BLE001
                self._error = (
                    f"配置下发失败(可先测DI): {exc} "
                    f"| 探测 DB{bridge.db_config}长度={size10}, "
                    f"DB{bridge.db_runtime}长度={size11}"
                )

    def _write_dq_force(self) -> None:
        if not bridge.connected:
            return
        packed = db_layout.pack_dq_force(self._dq_force)
        bridge.db_write(bridge.db_runtime, db_layout.DQ_FORCE_OFFSET, packed)
        if bridge.mock and self._cabinet:
            self._apply_dq_to_mock_q()

    def _apply_dq_to_mock_q(self) -> None:
        for s in self._cabinet.get("dq", []) or []:
            if not s.get("enable"):
                continue
            slot = int(s["slot"])
            start = int(s["start_addr"])
            n = min(int(s["channel_count"]), 32)
            force = self._dq_force[slot - 1]
            nbytes = (n + 7) // 8
            for bi in range(nbytes):
                byte_val = 0
                for bit in range(8):
                    ch = bi * 8 + bit
                    if ch < n and (force & (1 << ch)):
                        byte_val |= 1 << bit
                # write into mock Q image
                with bridge._lock:  # noqa: SLF001
                    if start + bi < len(bridge._mock_q):  # noqa: SLF001
                        bridge._mock_q[start + bi] = byte_val  # noqa: SLF001


    def inject_di_rising(self, start_addr: int, bit: int) -> Optional[int]:
        """Mock 专用：按过程映像地址注入一次 DI 上升沿播报（不依赖扫描时序）。
        返回槽内通道号（1..N），不累加全局号。"""
        with self._lock:
            cabinet = self._cabinet
            if not cabinet:
                return None
            gmap = db_layout.global_channel_map(cabinet, "di")
            for s in cabinet.get("di", []) or []:
                if not s.get("enable"):
                    continue
                start = int(s["start_addr"])
                n = int(s["channel_count"])
                slot = int(s["slot"])
                for ch in range(n):
                    byte_i = start + ch // 8
                    bit_i = ch % 8
                    if byte_i != start_addr or bit_i != bit:
                        continue
                    global_ch = next((g for g, ss, c in gmap if ss == slot and c == ch), None)
                    if global_ch is None:
                        return None
                    local_ch = ch + 1
                    self._prev_di[(slot, ch)] = True
                    self._di_states[global_ch] = True
                    self._active_di = local_ch
                    # 不入队：由前端按钮播报一次，避免与 poll 事件重复
                    return local_ch
            return None

    def inject_ai_change(self, start_addr: int, raw: int) -> Optional[tuple[int, float]]:
        """Mock 专用：按 AI 起始地址更新状态（播报由前端触发一次）。
        返回 (槽内通道号, mA)。"""
        with self._lock:
            cabinet = self._cabinet
            if not cabinet:
                return None
            gmap = db_layout.global_channel_map(cabinet, "ai")
            for s in cabinet.get("ai", []) or []:
                if not s.get("enable"):
                    continue
                if int(s["start_addr"]) != start_addr:
                    continue
                slot = int(s["slot"])
                conf = s
                raw_full = float(conf.get("raw_full", 27648) or 27648)
                eng_max = float(conf.get("eng_full_ma", 20.0) or 20.0)
                eng_min = float(conf.get("eng_min_ma", 4.0) or 4.0)
                if eng_max <= eng_min:
                    eng_min, eng_max = 4.0, 20.0
                span = eng_max - eng_min
                r = int(raw)
                if r >= 0x8000:
                    r -= 0x10000
                ma = eng_min + (r / raw_full) * span if raw_full else eng_min
                # Mock 按钮默认打通道 0（槽内第 1 路）
                ch = 0
                global_ch = next((g for g, ss, c in gmap if ss == slot and c == ch), None)
                if global_ch is None:
                    return None
                local_ch = ch + 1
                prev = self._prev_ai.get(global_ch)
                self._prev_ai[global_ch] = ma
                self._ai_values[global_ch] = ma
                self._active_ai = (local_ch, ma)
                self._ai_last_announce_ts = time.time()
                # 与真机一致：记下原值与本次值，回落到原值不再播
                if prev is not None:
                    self._mark_ai_seen(global_ch, prev, ma)
                else:
                    self._mark_ai_seen(global_ch, ma)
                # 不入队：由前端按钮播报一次
                return (local_ch, ma)
            return None

    def note_mock_di(self, start_addr: int, bit: int, value: bool) -> None:
        """Mock 拉低/置高时同步 prev，避免扫描线程再入队一次上升沿。"""
        with self._lock:
            cabinet = self._cabinet
            if not cabinet:
                return
            for s in cabinet.get("di", []) or []:
                if not s.get("enable"):
                    continue
                start = int(s["start_addr"])
                n = int(s["channel_count"])
                slot = int(s["slot"])
                for ch in range(n):
                    byte_i = start + ch // 8
                    bit_i = ch % 8
                    if byte_i == start_addr and bit_i == bit:
                        self._prev_di[(slot, ch)] = bool(value)
                        return

    def _loop(self) -> None:
        while True:
            # 整段扫描持锁，避免与 set_dq_bit 竞态把 Force 冲成 0
            with self._lock:
                if not self._running:
                    break
                cabinet = self._cabinet
                poll_ms = int(cabinet.get("plc", {}).get("poll_ms", 50)) if cabinet else 50
                try:
                    if bridge.connected and cabinet:
                        self._scan_once(cabinet)
                        self._error = None
                except Exception as exc:  # noqa: BLE001
                    self._error = str(exc)
            time.sleep(max(poll_ms, 20) / 1000.0)

    def _sync_dq_force_from_plc(self) -> None:
        """连接/下发时可选回读。扫描循环不要调用：错误回读会把本地 Force 冲成 0，
        而 PLC 上仍保持写入值，表现为「PLC 有输出、页面绿灯闪一下就灭」。"""
        try:
            raw_force = bridge.db_read(bridge.db_runtime, db_layout.DQ_FORCE_OFFSET, 80)
            if len(raw_force) >= 4:
                self._dq_force = db_layout.unpack_dq_force(raw_force)
        except Exception:  # noqa: BLE001
            pass

    def _dq_q_masks(self, cabinet: dict[str, Any]) -> list[int]:
        """从过程映像 Q 读出每槽位图，供页面绿灯显示。"""
        masks = [0] * 20
        for s in cabinet.get("dq", []) or []:
            if not s.get("enable"):
                continue
            slot = int(s["slot"])
            if not (1 <= slot <= 20):
                continue
            start = int(s.get("start_addr", 0))
            n = min(int(s.get("channel_count", 0)), 32)
            if n <= 0:
                continue
            nbytes = (n + 7) // 8
            try:
                data = bridge.read_area_q(start, nbytes)
            except Exception:  # noqa: BLE001
                continue
            bits = 0
            for ch in range(n):
                if ch // 8 < len(data) and (data[ch // 8] & (1 << (ch % 8))):
                    bits |= 1 << ch
            masks[slot - 1] = bits
        return masks

    def _scan_once(self, cabinet: dict[str, Any]) -> None:
        # AI：A→B（>10%）播 B；回到已测过的 A 不再播；1 秒内只播第一次
        thr_pct = float(cabinet.get("ai_announce_threshold_pct", 10.0)) / 100.0
        cooldown_s = float(cabinet.get("ai_announce_cooldown_ms", 1000)) / 1000.0
        now = time.time()
        # 注意：此处不再回读 DQ_Force；以 set_dq_bit/reset 维护的本地位图为准
        # DI：播报槽内通道 1..N，不累加全局号
        gmap = db_layout.global_channel_map(cabinet, "di")
        slots = {s["slot"]: s for s in cabinet.get("di", []) if s.get("enable")}
        for slot, conf in slots.items():
            start = int(conf["start_addr"])
            n = int(conf["channel_count"])
            nbytes = (n + 7) // 8
            data = bridge.read_area_i(start, nbytes)
            for ch in range(n):
                byte_i = ch // 8
                bit_i = ch % 8
                val = bool(data[byte_i] & (1 << bit_i))
                key = (slot, ch)
                prev = self._prev_di.get(key)
                global_ch = next((g for g, s, c in gmap if s == slot and c == ch), None)
                if global_ch is None:
                    continue
                local_ch = ch + 1
                self._di_states[global_ch] = val
                # 上升沿：False→True，以及首次 None→True（避免 Mock 短脉冲被跳过）
                if val and prev is not True:
                    self._active_di = local_ch
                    self._push_event(
                        AnnounceEvent(
                            kind="di",
                            channel=local_ch,
                            text=self._zh_number(local_ch),
                        )
                    )
                self._prev_di[key] = val

        # AI
        gmap_ai = db_layout.global_channel_map(cabinet, "ai")
        slots_ai = {s["slot"]: s for s in cabinet.get("ai", []) if s.get("enable")}
        for slot, conf in slots_ai.items():
            start = int(conf["start_addr"])
            n = int(conf["channel_count"])
            raw_full = float(conf.get("raw_full", 27648) or 27648)
            eng_max = float(conf.get("eng_full_ma", 20.0) or 20.0)
            eng_min = float(conf.get("eng_min_ma", 4.0) or 4.0)
            if eng_max <= eng_min:
                eng_min, eng_max = 4.0, 20.0
            span = eng_max - eng_min
            data = bridge.read_area_i(start, n * 2)
            for ch in range(n):
                hi, lo = data[ch * 2], data[ch * 2 + 1]
                raw = (hi << 8) | lo
                if raw >= 0x8000:
                    raw -= 0x10000
                # 4~20mA 组态：0→eng_min，27648→eng_max
                ma = eng_min + (raw / raw_full) * span if raw_full else eng_min
                global_ch = next((g for g, s, c in gmap_ai if s == slot and c == ch), None)
                if global_ch is None:
                    continue
                local_ch = ch + 1
                self._ai_values[global_ch] = ma
                prev = self._prev_ai.get(global_ch)
                ma_i = self._ma_announce_key(ma)
                seen = self._ai_seen_ma.get(global_ch) or set()
                # 首次只记基准原值 A，不播报；仅在 A→B 且变化够大时播 B
                should = False
                if prev is not None and ma_i not in seen:
                    base = abs(prev) if abs(prev) > 1e-6 else max(span * 0.1, 1.0)
                    should = abs(ma - prev) >= base * thr_pct
                if should and (now - self._ai_last_announce_ts) >= cooldown_s:
                    self._active_ai = (local_ch, ma)
                    ma_txt = self._zh_ma(ma)
                    self._push_event(
                        AnnounceEvent(
                            kind="ai",
                            channel=local_ch,
                            ma=ma,
                            text=f"{self._zh_number(local_ch)}，{ma_txt}",
                        )
                    )
                    self._ai_last_announce_ts = now
                    # 原值 A 与本次 B 都记入已测，回落 A 或再遇 B 不再播
                    self._mark_ai_seen(global_ch, prev, ma)
                self._prev_ai[global_ch] = ma

        # AQ monitor from runtime DB（块不存在时不阻断 DI/AI）
        try:
            rt = bridge.db_read(bridge.db_runtime, 0, db_layout.RUNTIME_DB_SIZE)
            vals = db_layout.unpack_aq_ma(rt)
        except Exception:  # noqa: BLE001
            vals = []
        expected: list[float] = []
        g = 0
        for s in sorted(cabinet.get("aq", []), key=lambda x: x["slot"]):
            if not s.get("enable"):
                continue
            for _ in range(int(s["channel_count"])):
                g += 1
                expected.append(float(4 + ((g - 1) % 8)))  # 4~11 循环
        if not vals or all(abs(v) < 1e-6 for v in vals[: len(expected)]):
            self._aq_values = expected
        else:
            self._aq_values = vals[: len(expected)] if expected else vals

    @staticmethod
    def _zh_number(n: int) -> str:
        """两位数简化：>20 不读「十」，如 21→二一，加快播报。"""
        digits = "零一二三四五六七八九"
        n = int(n)
        if n < 0:
            n = 0
        if n <= 10:
            return ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][n]
        if n < 20:
            return "十" + (digits[n - 10] if n > 10 else "")
        if n < 100:
            tens, ones = divmod(n, 10)
            if ones == 0:
                return digits[tens] + "十"  # 20→二十
            # >20：不读「十」→ 二一、三二等
            return digits[tens] + digits[ones]
        return str(n)

    @staticmethod
    def _zh_ma(ma: float) -> str:
        n = int(round(ma))
        if n < 0:
            n = 0
        if n > 24:
            return "超出二十四毫安"
        return f"{IoScanner._zh_number(n)}毫安"

    @staticmethod
    def _zh_number_tts(n: int) -> str:
        """TTS 文案：>20 用顿号，避免念成「三十一」。"""
        digits = "零一二三四五六七八九"
        n = int(n)
        if n <= 20 or (n < 100 and n % 10 == 0):
            return IoScanner._zh_number(n)
        if n < 100:
            tens, ones = divmod(n, 10)
            return f"{digits[tens]}、{digits[ones]}"
        return str(n)


scanner = IoScanner()
