#!/usr/bin/env python3
"""Convert TIA Openness CAx AML export → checkPLC cabinet JSON.

Usage:
  python scripts/aml_to_cabinet.py export.aml -o configs/柜A.json --name 柜A --ip 192.168.0.1

AML comes from tools/tia-openness-export (CaxProvider.Export).
Namespaces and nesting vary by TIA version; this parser matches Attribute/@Name
flexibly and classifies Digital/Analog × Input/Output into di/dq/ai/aq.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

SLOTS = 20
DIG_DEFAULT_CH = 16
ANA_DEFAULT_CH = 8


def local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def attr_name(el: ET.Element) -> str:
    return (el.get("Name") or el.get("name") or "").strip()


def text_of(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    # Direct text or child <Value>
    if el.text and el.text.strip():
        return el.text.strip()
    for c in el:
        if local(c.tag).lower() in {"value", "val"}:
            return (c.text or "").strip()
    return ""


def find_named_attrs(root: ET.Element) -> list[tuple[ET.Element, str]]:
    """All Attribute-like elements with a Name."""
    out: list[tuple[ET.Element, str]] = []
    for el in root.iter():
        ln = local(el.tag).lower()
        if ln in {"attribute", "attr"}:
            n = attr_name(el)
            if n:
                out.append((el, n))
    return out


def nested_attr_map(el: ET.Element) -> dict[str, str]:
    """Map child Attribute Name → Value for one Attribute parent."""
    m: dict[str, str] = {}
    for c in el:
        if local(c.tag).lower() not in {"attribute", "attr"}:
            continue
        n = attr_name(c)
        if not n:
            continue
        m[n] = text_of(c)
        # also flatten one more level (Address → IoType/StartAddress/Length)
        for gc in c:
            if local(gc.tag).lower() in {"attribute", "attr"}:
                gn = attr_name(gc)
                if gn:
                    m[gn] = text_of(gc)
    # self value
    if text_of(el) and attr_name(el):
        m.setdefault(attr_name(el), text_of(el))
    return m


def nearest_device_name(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    cur: Optional[ET.Element] = el
    while cur is not None:
        ln = local(cur.tag).lower()
        if ln in {"internalelement", "externalinterface", "element", "deviceitem", "module"}:
            name = cur.get("Name") or cur.get("name") or ""
            if name and not name.startswith("System:"):
                return name
        cur = parents.get(cur)
    return ""


def build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parents: dict[ET.Element, ET.Element] = {}
    for p in root.iter():
        for c in p:
            parents[c] = p
    return parents


def parse_int(s: str, default: int = 0) -> int:
    s = (s or "").strip()
    if not s or s == "-1":
        return default
    try:
        # allow "0" / "64" / "0.0" style
        if "." in s:
            return int(float(s))
        return int(s, 10)
    except ValueError:
        m = re.search(r"-?\d+", s)
        return int(m.group(0)) if m else default


# CPU 高速计数/脉冲、驱动 PZD、通信模块等不是柜体检的 DI/DQ/AI/AQ
_SKIP_MODULE = re.compile(
    r"(?ix)"
    r"(^HSC(_|\d|$))"
    r"|(^Pulse(_|\d|$))"
    r"|(\bPTO\b)"
    r"|(PZD)"
    r"|(任意报文)"
    r"|(Free\s*telegram)"
    r"|(^CM\s*\d)"
    r"|(\bCM\s*12)"
    r"|(PosInput)"
    r"|(^TM\s)"
    r"|(PROFINET)"
    r"|(OPC\s*UA)"
)

_KIND_FROM_CH = {
    "DI": "di",
    "DO": "dq",
    "DQ": "dq",
    "AI": "ai",
    "AQ": "aq",
    "AO": "aq",
}


def skip_module(name: str) -> bool:
    n = (name or "").strip()
    if not n or n.startswith("System:"):
        return True
    return _SKIP_MODULE.search(n) is not None


def _has_di(n: str) -> bool:
    return bool(re.search(r"(?<![A-Z])DI(?:\d+|\s+\d+|\b)", n))


def _has_dq(n: str) -> bool:
    return bool(re.search(r"(?<![A-Z])(?:DQ|DO)(?:\d+|\s+\d+|\b)", n))


def _has_ai(n: str) -> bool:
    return bool(re.search(r"(?<![A-Z])AI(?:\d+|\s+\d+|\b)|ANALOG.?IN", n))


def _has_aq(n: str) -> bool:
    return bool(re.search(r"(?<![A-Z])(?:AQ|AO)(?:\d+|\s+\d+|\b)|ANALOG.?OUT", n))


def _io_is_output(io: str) -> bool:
    return "out" in io


def _io_is_input(io: str) -> bool:
    return "in" in io and "out" not in io


def classify(io_type: str, signal_type: str, length: int, name: str) -> Optional[str]:
    if skip_module(name):
        return None
    io = (io_type or "").lower()
    sig = (signal_type or "").lower()
    n = (name or "").upper()

    # 集成 DI/DQ、AI/AQ：必须按 IoType 拆成两条，不能只看名字里先出现的 DQ/AQ
    if _has_di(n) and _has_dq(n):
        if _io_is_output(io):
            return "dq"
        if _io_is_input(io):
            return "di"
        return None
    if _has_ai(n) and _has_aq(n):
        if _io_is_output(io):
            return "aq"
        if _io_is_input(io):
            return "ai"
        return None

    if "analog" in sig or sig in {"ai", "ao", "aq"}:
        if _io_is_output(io) or "aq" in sig or "ao" in sig:
            return "aq"
        return "ai"
    if "digital" in sig or sig in {"di", "do", "dq"}:
        if _io_is_output(io) or "dq" in sig or "do" in sig:
            return "dq"
        return "di"

    if _has_aq(n):
        return "aq"
    if _has_ai(n):
        return "ai"
    if _has_dq(n):
        return "dq"
    if _has_di(n):
        return "di"

    # 无名模块：按方向归入数字量，避免把 DI16 的 Length=16 误判成 AI
    if _io_is_output(io):
        return "dq"
    if _io_is_input(io):
        return "di"
    return None


def _channels_from_name(kind: str, name: str) -> int:
    n = (name or "").upper()
    if kind == "di":
        pat = r"(?<![A-Z])DI\s*(\d+)"
    elif kind == "dq":
        pat = r"(?<![A-Z])(?:DQ|DO)\s*(\d+)"
    elif kind == "ai":
        pat = r"(?<![A-Z])AI\s*(\d+)"
    else:
        pat = r"(?<![A-Z])(?:AQ|AO)\s*(\d+)"
    m = re.search(pat, n)
    return int(m.group(1)) if m else 0


def channel_count_from(kind: str, length: int, channel_nums: set[int], name: str) -> int:
    from_ch = (max(channel_nums) + 1) if channel_nums else 0
    from_name = _channels_from_name(kind, name)

    if kind in {"ai", "aq"}:
        if from_ch > 1:
            return max(1, min(from_ch, 8))
        if from_name:
            return max(1, min(from_name, 8))
        if length >= 16:
            return max(1, min(length // 16, 8))
        return ANA_DEFAULT_CH

    # 数字量：DI14 的 AML Length 常为 16（按字对齐），通道名/Channel_* 更准
    if from_ch > 1:
        return max(1, min(from_ch, 32))
    if from_name:
        return max(1, min(from_name, 32))
    if from_ch > 0:
        return max(1, min(from_ch, 32))
    if length > 0:
        return max(1, min(length, 32))
    return DIG_DEFAULT_CH


def empty_dig_slot(slot: int, enable: bool = False, start: int = 0, ch: int = DIG_DEFAULT_CH, name: str = "") -> dict:
    return {
        "slot": slot,
        "enable": enable,
        "start_addr": start,
        "channel_count": ch,
        "name": name,
    }


def empty_ana_slot(slot: int, enable: bool = False, start: int = 0, ch: int = ANA_DEFAULT_CH, name: str = "") -> dict:
    return {
        "slot": slot,
        "enable": enable,
        "start_addr": start,
        "channel_count": ch,
        "name": name,
        "raw_full": 27648,
        "eng_min_ma": 4,
        "eng_full_ma": 20,
    }


def pad_slots(kind: str, enabled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(enabled[:SLOTS], start=1):
        item = dict(item)
        item["slot"] = i
        item["enable"] = True
        out.append(item)
    while len(out) < SLOTS:
        s = len(out) + 1
        out.append(empty_dig_slot(s) if kind in {"di", "dq"} else empty_ana_slot(s))
    return out


def iter_address_slots(addr_el: ET.Element) -> list[dict[str, str]]:
    """V21 CAx: Address → Attribute '1'/'2' each with StartAddress/Length/IoType.
    Older/demo: Address 直接挂 IoType/StartAddress/Length。"""
    numbered: list[dict[str, str]] = []
    flat: dict[str, str] = {}
    for c in addr_el:
        if local(c.tag).lower() not in {"attribute", "attr"}:
            continue
        n = attr_name(c)
        if n.isdigit():
            inner: dict[str, str] = {}
            for gc in c:
                if local(gc.tag).lower() in {"attribute", "attr"}:
                    gn = attr_name(gc)
                    if gn:
                        inner[gn] = text_of(gc)
            numbered.append(inner)
        elif n in {"StartAddress", "IoType", "Length", "Type"}:
            flat[n] = text_of(c)
    if numbered:
        return numbered
    if flat.get("StartAddress") not in (None, ""):
        return [flat]
    return []


def channels_from_module(mod_el: ET.Element) -> dict[str, set[int]]:
    by_kind: dict[str, set[int]] = {"di": set(), "dq": set(), "ai": set(), "aq": set()}
    mod_name = mod_el.get("Name") or mod_el.get("name") or ""
    for c in mod_el:
        ln = local(c.tag).lower()
        name = c.get("Name") or c.get("name") or ""
        if ln == "externalinterface":
            m = re.match(r"Channel_(DI|DO|DQ|AI|AQ|AO)_(\d+)$", name, re.I)
            if not m:
                continue
            kind = _KIND_FROM_CH.get(m.group(1).upper())
            if kind:
                by_kind[kind].add(int(m.group(2)))
            continue
        if ln in {"attribute", "attr"} and name == "Channel":
            am = nested_attr_map(c)
            kind = classify(am.get("IoType", ""), am.get("Type", ""), 0, mod_name)
            if kind:
                by_kind[kind].add(parse_int(am.get("Number", "0"), 0))
    return by_kind


def nearest_station(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    cur: Optional[ET.Element] = el
    while cur is not None:
        if local(cur.tag).lower() == "internalelement":
            name = cur.get("Name") or cur.get("name") or ""
            tid = ""
            for c in cur:
                if local(c.tag).lower() in {"attribute", "attr"} and attr_name(c) == "TypeIdentifier":
                    tid = text_of(c)
                    break
            if "station" in name.lower() or "Device." in tid:
                return name
        cur = parents.get(cur)
    return ""


def short_station(name: str) -> str:
    m = re.search(r"station[_\s]?\d+", name or "", re.I)
    return m.group(0) if m else (name or "")


def _under_device(el: ET.Element, parents: dict[ET.Element, ET.Element], needle: str) -> bool:
    cur: Optional[ET.Element] = el
    while cur is not None:
        n = (cur.get("Name") or cur.get("name") or "").lower()
        if needle in n:
            return True
        cur = parents.get(cur)
    return False


def extract_modules(root: ET.Element, device: str = "") -> list[dict[str, Any]]:
    """Collect one IO record per Address slot (combo DI/DQ 会拆成两条)."""
    parents = build_parent_map(root)
    device_l = (device or "").strip().lower()
    buckets: dict[tuple[str, str, str, int], dict[str, Any]] = {}

    for el in root.iter():
        if local(el.tag).lower() != "internalelement":
            continue
        mod = el.get("Name") or el.get("name") or ""
        if skip_module(mod):
            continue
        slots: list[dict[str, str]] = []
        for c in el:
            if local(c.tag).lower() not in {"attribute", "attr"}:
                continue
            if attr_name(c) != "Address":
                continue
            slots.extend(iter_address_slots(c))
        if not slots:
            continue
        if device_l and not _under_device(el, parents, device_l):
            continue
        station = nearest_station(el, parents)
        ch_by_kind = channels_from_module(el)
        for rec in slots:
            start = parse_int(rec.get("StartAddress", "-1"), -1)
            if start < 0:
                continue
            length = parse_int(rec.get("Length", "0"), 0)
            io_type = rec.get("IoType", "")
            kind = classify(io_type, rec.get("Type", ""), length, mod)
            if not kind:
                continue
            key = (station, mod, kind, start)
            b = buckets.setdefault(
                key,
                {
                    "name": mod,
                    "station": station,
                    "kind": kind,
                    "start_addr": start,
                    "length": length,
                    "channels": set(ch_by_kind.get(kind) or ()),
                },
            )
            if length:
                b["length"] = length

    return list(buckets.values())


def guess_ip(root: ET.Element) -> Optional[str]:
    for el, name in find_named_attrs(root):
        n = name.lower()
        if n in {"ipaddress", "address", "ipv4address", "ip"}:
            v = text_of(el)
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", v):
                # skip 0.0.0.0
                if v != "0.0.0.0":
                    return v
        # nested
        m = nested_attr_map(el)
        for k, v in m.items():
            if "ip" in k.lower() and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", v) and v != "0.0.0.0":
                return v
    return None


def with_kind_index(seq: int, raw: str) -> str:
    """Prefix 1. 2. 3. … so identical catalog names stay distinguishable."""
    raw = (raw or "").strip()
    raw = re.sub(r"^\d+\.", "", raw).strip()
    return f"{seq}.{raw}" if raw else str(seq)


def modules_to_cabinet(
    modules: list[dict[str, Any]],
    name: str,
    ip: str,
) -> dict[str, Any]:
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # stable order by start address then name
    modules_sorted = sorted(modules, key=lambda m: (m["kind"], m["start_addr"], m["name"]))
    kind_seq: dict[str, int] = defaultdict(int)
    stations = {str(m.get("station") or "") for m in modules_sorted if m.get("station")}
    multi_station = len(stations) > 1
    for m in modules_sorted:
        kind = m["kind"]
        kind_seq[kind] += 1
        raw = m.get("name") or ""
        if multi_station and m.get("station"):
            raw = f"{short_station(str(m['station']))} / {raw}"
        labeled = with_kind_index(kind_seq[kind], raw)
        ch = channel_count_from(kind, int(m.get("length") or 0), m.get("channels") or set(), m.get("name") or "")
        # clamp sensible ranges
        if kind in {"di", "dq"}:
            ch = max(1, min(ch, 32))
            item = empty_dig_slot(0, True, int(m["start_addr"]), ch, labeled)
        else:
            ch = max(1, min(ch, 8))
            item = empty_ana_slot(0, True, int(m["start_addr"]), ch, labeled)
        by_kind[kind].append(item)

    truncated = {k: len(v) for k, v in by_kind.items() if len(v) > SLOTS}

    cab = {
        "name": name,
        "plc": {
            "ip": ip,
            "rack": 0,
            "slot": 1,
            "db_config": 810,
            "db_runtime": 811,
            "poll_ms": 50,
        },
        "di": pad_slots("di", by_kind.get("di", [])),
        "dq": pad_slots("dq", by_kind.get("dq", [])),
        "ai": pad_slots("ai", by_kind.get("ai", [])),
        "aq": pad_slots("aq", by_kind.get("aq", [])),
        "ai_announce_threshold_pct": 10,
        "ai_announce_cooldown_ms": 1000,
        "ai_settle_ms": 300,
        "_import": {
            "source": "tia_cax_aml",
            "stations": sorted(stations),
            "truncated": truncated,
            "modules_found": [
                {
                    "kind": m["kind"],
                    "name": m.get("name"),
                    "station": m.get("station"),
                    "start_addr": m["start_addr"],
                    "length": m.get("length"),
                    "channels": sorted(m.get("channels") or []),
                }
                for m in modules_sorted
            ],
        },
    }
    return cab


def main() -> int:
    ap = argparse.ArgumentParser(description="TIA CAx AML → checkPLC cabinet JSON")
    ap.add_argument("aml", type=Path, help="Path to .aml exported by Openness CaxProvider")
    ap.add_argument("-o", "--output", type=Path, help="Output JSON path (default: configs/<name>.json)")
    ap.add_argument("--name", default="", help="Cabinet config name (default: AML stem)")
    ap.add_argument("--ip", default="", help="PLC IP (override; else try AML, else 192.168.0.1)")
    ap.add_argument("--dry-run", action="store_true", help="Print summary only, do not write")
    args = ap.parse_args()

    if not args.aml.exists():
        print(f"AML not found: {args.aml}", file=sys.stderr)
        return 1

    try:
        tree = ET.parse(str(args.aml))
    except ET.ParseError as exc:
        print(f"Invalid XML/AML: {exc}", file=sys.stderr)
        return 1

    root = tree.getroot()
    modules = extract_modules(root)
    if not modules:
        print(
            "未在 AML 中解析到带 StartAddress 的 IO 模块。\n"
            "请确认：1) CAx 导出成功 2) 工程含 DI/DQ/AI/AQ 3) 把本 AML 发回以便适配命名空间。",
            file=sys.stderr,
        )
        return 2

    name = args.name.strip() or args.aml.stem
    ip = args.ip.strip() or guess_ip(root) or "192.168.0.1"
    cab = modules_to_cabinet(modules, name, ip)

    summary = {
        k: sum(1 for s in cab[k] if s.get("enable")) for k in ("di", "dq", "ai", "aq")
    }
    print(f"解析模块 {len(modules)} 个 → 启用槽 DI:{summary['di']} DQ:{summary['dq']} AI:{summary['ai']} AQ:{summary['aq']}")
    print(f"PLC IP: {ip}")
    truncated = cab.get("_import", {}).get("truncated") or {}
    if truncated:
        extra = " ".join(f"{k.upper()}共{n}个(已截到{SLOTS})" for k, n in truncated.items())
        print(f"注意: 每类最多 {SLOTS} 槽，{extra}。可在导出时填写「站名」只导出当前 PLC。")
    for m in cab.get("_import", {}).get("modules_found", []):
        st = m.get("station") or ""
        prefix = f"{st} " if st else ""
        print(f"  [{m['kind']}] {prefix}{m['name']}  start={m['start_addr']}  len={m['length']}  ch={m['channels']}")

    if args.dry_run:
        return 0

    out = args.output
    if out is None:
        root_dir = Path(__file__).resolve().parents[1]
        out = root_dir / "configs" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Web 加载不需要 _import 也可保留便于追溯
    out.write_text(json.dumps(cab, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out}")
    print("Web：配置页加载该配置名即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
