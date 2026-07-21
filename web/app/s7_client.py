"""S7 client with optional mock mode (no PLC)."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

try:
    from snap7 import client as snap7_client

    try:
        from snap7.type import Areas as S7Areas
        from snap7.type import Block as S7Block
    except ImportError:  # pragma: no cover
        from snap7.types import Areas as S7Areas  # type: ignore

        S7Block = None  # type: ignore

    HAS_SNAP7 = True
except Exception:  # noqa: BLE001
    HAS_SNAP7 = False
    snap7_client = None  # type: ignore
    S7Areas = None  # type: ignore
    S7Block = None  # type: ignore


class S7Bridge:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client = snap7_client.Client() if HAS_SNAP7 else None
        self.connected = False
        self.mock = False
        self.ip = ""
        self.rack = 0
        self.slot = 1
        self.db_config = 10
        self.db_runtime = 11
        self._mock_i = bytearray(256)
        self._mock_q = bytearray(256)
        self._mock_db10 = bytearray(960)
        self._mock_db11 = bytearray(724)

    def connect(self, ip: str, rack: int = 0, slot: int = 1, mock: bool = False) -> None:
        with self._lock:
            self.disconnect()
            self.ip = ip
            self.rack = rack
            self.slot = slot
            self.mock = mock or (not HAS_SNAP7)
            if self.mock:
                self.connected = True
                logger.info("S7 mock connected ip=%s", ip)
                return
            assert self._client is not None
            try:
                self._client.set_connection_type(3)
            except Exception:  # noqa: BLE001
                pass
            try:
                self._client.connect(ip, rack, slot)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._friendly_s7_error(exc)) from exc
            self.connected = True
            logger.info("S7 connected %s rack=%s slot=%s", ip, rack, slot)

    def disconnect(self) -> None:
        # 先清标志，避免扫描线程占着锁时「断开」按钮一直无响应
        self.connected = False
        self.mock = False
        with self._lock:
            if self._client:
                try:
                    if self._client.get_connected():
                        self._client.disconnect()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _friendly_s7_error(exc: BaseException, db_number: int | None = None) -> str:
        msg = str(exc)
        low = msg.lower()
        if "0x05" in low or "invalid address" in low:
            db_hint = f"DB{db_number}" if db_number is not None else "目标 DB"
            return (
                f"{msg}\n"
                f"【Invalid address 0x05】写入 {db_hint} 失败，常见原因：\n"
                "1) 该 DB 仍是「优化的块访问」→ 属性里取消优化，重新下载；\n"
                "2) 块编号不是 Web 填的 10/11（看 DB 属性里的编号，改 Web 连接页）；\n"
                "3) DB 未下载到 CPU，或名称对但编号不同。\n"
                "DI 可读过程映像可先测；DQ 强制必须能写运行 DB。"
            )
        if "0x04" in low or "not implemented" in low or "0x81" in low:
            return (
                f"{msg}\n"
                "【PUT/GET】请勾选「允许来自远程对象的 PUT/GET 通信」并重新下载。"
            )
        return msg

    def read_area_i(self, start: int, size: int) -> bytes:
        with self._lock:
            self._ensure()
            if self.mock:
                return bytes(self._mock_i[start : start + size])
            assert self._client is not None and S7Areas is not None
            try:
                return bytes(self._client.read_area(S7Areas.PE, 0, start, size))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._friendly_s7_error(exc)) from exc

    def read_area_q(self, start: int, size: int) -> bytes:
        with self._lock:
            self._ensure()
            if self.mock:
                return bytes(self._mock_q[start : start + size])
            assert self._client is not None and S7Areas is not None
            try:
                return bytes(self._client.read_area(S7Areas.PA, 0, start, size))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._friendly_s7_error(exc)) from exc

    def db_read(self, db_number: int, start: int, size: int) -> bytes:
        with self._lock:
            self._ensure()
            if self.mock:
                src = self._mock_db10 if db_number == self.db_config else self._mock_db11
                return bytes(src[start : start + size])
            assert self._client is not None
            try:
                return bytes(self._client.db_read(db_number, start, size))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._friendly_s7_error(exc, db_number)) from exc

    def get_db_size(self, db_number: int) -> int:
        with self._lock:
            self._ensure()
            if self.mock:
                return 960 if db_number == self.db_config else 724
            assert self._client is not None and S7Block is not None
            try:
                info = self._client.get_block_info(S7Block.DB, db_number)
                return int(info.MC7Size)
            except Exception:  # noqa: BLE001
                return -1

    def db_write(self, db_number: int, start: int, data: bytes | bytearray) -> None:
        with self._lock:
            self._ensure()
            if self.mock:
                dst = self._mock_db10 if db_number == self.db_config else self._mock_db11
                dst[start : start + len(data)] = data
                return
            assert self._client is not None
            payload = bytearray(data)
            try:
                # 直接取块信息，避免嵌套锁逻辑复杂化
                size = -1
                if S7Block is not None:
                    try:
                        size = int(self._client.get_block_info(S7Block.DB, db_number).MC7Size)
                    except Exception:  # noqa: BLE001
                        size = -1
                if size > 0 and start + len(payload) > size:
                    allow = size - start
                    if allow <= 0:
                        raise RuntimeError(
                            f"DB{db_number} 长度仅 {size} 字节，无法从偏移 {start} 写入。"
                            "请确认块编号，并取消优化访问后重新下载。"
                        )
                    logger.warning(
                        "DB%s size=%s, truncate write %s -> %s",
                        db_number,
                        size,
                        len(payload),
                        allow,
                    )
                    payload = payload[:allow]
                self._client.db_write(db_number, start, payload)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(self._friendly_s7_error(exc, db_number)) from exc

    def mock_set_di_bit(self, byte_addr: int, bit: int, value: bool) -> None:
        with self._lock:
            if value:
                self._mock_i[byte_addr] |= 1 << bit
            else:
                self._mock_i[byte_addr] &= ~(1 << bit)

    def mock_set_ai_raw(self, byte_addr: int, raw: int) -> None:
        with self._lock:
            self._mock_i[byte_addr] = (raw >> 8) & 0xFF
            self._mock_i[byte_addr + 1] = raw & 0xFF

    def _ensure(self) -> None:
        if not self.connected:
            raise RuntimeError("未连接 PLC")


bridge = S7Bridge()
