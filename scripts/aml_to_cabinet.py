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


def classify(io_type: str, signal_type: str, length: int, name: str) -> Optional[str]:
    io = (io_type or "").lower()
    sig = (signal_type or "").lower()
    n = (name or "").upper()

    # Prefer explicit channel type
    if "analog" in sig or sig in {"ai", "ao", "aq"}:
        if "out" in io or "output" in io or "aq" in sig or "ao" in sig:
            return "aq"
        return "ai"
    if "digital" in sig or sig in {"di", "do", "dq"}:
        if "out" in io or "output" in io or "dq" in sig or "do" in sig:
            return "dq"
        return "di"

    # Heuristic from module name
    if re.search(r"\bAQ\b|ANALOG.?OUT|AO\b", n):
        return "aq"
    if re.search(r"\bAI\b|ANALOG.?IN", n):
        return "ai"
    if re.search(r"\bDQ\b|DO\b|DIGITAL.?OUT", n):
        return "dq"
    if re.search(r"\bDI\b|DIGITAL.?IN", n):
        return "di"
    if "DI" in n and "DQ" in n:
        # integrated — caller splits by IoType
        if "out" in io or "output" in io:
            return "dq"
        if "in" in io or "input" in io:
            return "di"

    # Length heuristic: analog channels often 16 bits per channel in AML docs
    if "out" in io or "output" in io:
        return "aq" if length >= 16 and length % 16 == 0 and length <= 128 else "dq"
    if "in" in io or "input" in io:
        return "ai" if length >= 16 and length % 16 == 0 and length <= 128 else "di"
    return None


def channel_count_from(kind: str, length: int, channel_nums: set[int], name: str) -> int:
    from_ch = (max(channel_nums) + 1) if channel_nums else 0
    n = (name or "").upper()
    m = re.search(r"(?:DI|DQ|DO|AI|AQ|AO)\s*(\d+)", n)
    from_name = int(m.group(1)) if m else 0

    if kind in {"ai", "aq"}:
        # 模拟量：优先通道跨度；否则 Length/16；再否则模块名中的点数
        if from_ch > 1:
            return max(1, min(from_ch, 8))
        if length >= 16:
            return max(1, min(length // 16, 8))
        if from_name:
            return max(1, min(from_name, 8))
        return ANA_DEFAULT_CH

    # 数字量：AML Length 通常为总位数，优先于单个 Channel 样例
    if length > 0:
        return max(1, min(length, 32))
    if from_name:
        return max(1, min(from_name, 32))
    if from_ch > 0:
        return max(1, min(from_ch, 32))
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


def extract_modules(root: ET.Element) -> list[dict[str, Any]]:
    """Collect address records from AML."""
    parents = build_parent_map(root)
    # Group by (module_name, io_type, start) accumulating channels
    buckets: dict[tuple[str, str, int], dict[str, Any]] = {}

    for el, name in find_named_attrs(root):
        # Look for Address blocks or StartAddress leaves
        if name not in {"Address", "StartAddress", "IoType", "Channel"}:
            continue

        # Climb to a container that holds Address children
        node = el
        # If this is StartAddress, go to parent Address if any
        if name == "StartAddress":
            p = parents.get(el)
            if p is not None and attr_name(p) == "Address":
                node = p
            else:
                # standalone StartAddress — build synthetic
                io_type = ""
                length = 0
                start = parse_int(text_of(el), -1)
                if start < 0:
                    continue
                mod = nearest_device_name(el, parents)
                kind = classify(io_type, "", length, mod)
                if not kind:
                    continue
                key = (mod, kind, start)
                buckets.setdefault(
                    key,
                    {"name": mod, "kind": kind, "start_addr": start, "length": length, "channels": set()},
                )
                continue

        if name == "Channel":
            # Channel under a device item — gather type/number; address may be sibling
            ch_map = nested_attr_map(el)
            ch_type = ch_map.get("Type", "")
            ch_io = ch_map.get("IoType", "")
            ch_num = parse_int(ch_map.get("Number", "0"), 0)
            mod = nearest_device_name(el, parents)
            # find sibling/parent Address
            start = -1
            length = 0
            io_type = ch_io
            cur = parents.get(el)
            depth = 0
            matched_addr: Optional[dict[str, str]] = None
            while cur is not None and depth < 6:
                for c in cur:
                    if local(c.tag).lower() not in {"attribute", "attr"}:
                        continue
                    if attr_name(c) != "Address":
                        continue
                    am = nested_attr_map(c)
                    for gc in c:
                        if local(gc.tag).lower() in {"attribute", "attr"}:
                            am[attr_name(gc)] = text_of(gc)
                    addr_io = (am.get("IoType") or "").lower()
                    ch_io_l = (ch_io or "").lower()
                    # Prefer address with same IoType as channel
                    if ch_io_l and addr_io and (
                        ("out" in ch_io_l and "out" in addr_io)
                        or ("in" in ch_io_l and "in" in addr_io and "out" not in addr_io)
                    ):
                        matched_addr = am
                        break
                    if matched_addr is None and am.get("StartAddress"):
                        matched_addr = am
                if matched_addr is not None:
                    break
                cur = parents.get(cur)
                depth += 1
            if matched_addr:
                start = parse_int(matched_addr.get("StartAddress", "-1"), -1)
                length = parse_int(matched_addr.get("Length", "0"), 0)
                if not io_type:
                    io_type = matched_addr.get("IoType", "")
            if start < 0:
                # channel-only; skip if no address (cannot place in process image)
                continue
            kind = classify(io_type, ch_type, length, mod)
            if not kind:
                continue
            key = (mod, kind, start)
            b = buckets.setdefault(
                key,
                {"name": mod, "kind": kind, "start_addr": start, "length": length, "channels": set()},
            )
            b["channels"].add(ch_num)
            # 不覆盖 Address 阶段已写入的正确 Length（集成 DI/DQ 易被通道侧误匹配）
            if length and not b.get("length"):
                b["length"] = length
            continue

        if name == "Address":
            am = nested_attr_map(el)
            # also read direct children
            for c in el:
                if local(c.tag).lower() in {"attribute", "attr"}:
                    am[attr_name(c)] = text_of(c)
            start = parse_int(am.get("StartAddress", "-1"), -1)
            if start < 0:
                continue
            length = parse_int(am.get("Length", "0"), 0)
            io_type = am.get("IoType", "")
            mod = nearest_device_name(el, parents)
            kind = classify(io_type, "", length, mod)
            if not kind:
                continue
            key = (mod, kind, start)
            buckets.setdefault(
                key,
                {"name": mod, "kind": kind, "start_addr": start, "length": length, "channels": set()},
            )
            if length:
                buckets[key]["length"] = length

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


def modules_to_cabinet(
    modules: list[dict[str, Any]],
    name: str,
    ip: str,
) -> dict[str, Any]:
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # stable order by start address then name
    modules_sorted = sorted(modules, key=lambda m: (m["kind"], m["start_addr"], m["name"]))
    for m in modules_sorted:
        kind = m["kind"]
        ch = channel_count_from(kind, int(m.get("length") or 0), m.get("channels") or set(), m.get("name") or "")
        # clamp sensible ranges
        if kind in {"di", "dq"}:
            ch = max(1, min(ch, 32))
            item = empty_dig_slot(0, True, int(m["start_addr"]), ch, m.get("name") or "")
        else:
            ch = max(1, min(ch, 8))
            item = empty_ana_slot(0, True, int(m["start_addr"]), ch, m.get("name") or "")
        by_kind[kind].append(item)

    cab = {
        "name": name,
        "plc": {
            "ip": ip,
            "rack": 0,
            "slot": 1,
            "db_config": 10,
            "db_runtime": 11,
            "poll_ms": 50,
        },
        "di": pad_slots("di", by_kind.get("di", [])),
        "dq": pad_slots("dq", by_kind.get("dq", [])),
        "ai": pad_slots("ai", by_kind.get("ai", [])),
        "aq": pad_slots("aq", by_kind.get("aq", [])),
        "ai_announce_threshold_pct": 10,
        "ai_announce_cooldown_ms": 1000,
        "_import": {
            "source": "tia_cax_aml",
            "modules_found": [
                {
                    "kind": m["kind"],
                    "name": m.get("name"),
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
    for m in cab.get("_import", {}).get("modules_found", []):
        print(f"  [{m['kind']}] {m['name']}  start={m['start_addr']}  len={m['length']}  ch={m['channels']}")

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
