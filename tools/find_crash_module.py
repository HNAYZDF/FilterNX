#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_crash_module.py — 在 SD 卡上找出崩溃报告对应的模块

Atmosphère 的 crash_reports 文件名形如:
    <pid>_<build_id>_thread_info.bin
其中 build_id 是崩溃进程的 NSO/NRO build id。

本脚本扫描卡上所有可执行容器（.nro / .ovl / .nsp / .kip），
提取各自的 build id，找出与崩溃报告匹配的那一个。
"""

import struct
import sys
from pathlib import Path

CARD = Path("G:/")


def nro_build_id(b: bytes):
    """NRO: NroStart(0x10) 之后是 NroHeader，build_id 在文件偏移 0x38"""
    if len(b) < 0x58:
        return None
    magic = b[0x10:0x14]
    if magic != b"NRO0":
        return None
    return b[0x38:0x58].rstrip(b"\x00").hex()


def nso_build_id(b: bytes):
    """NSO: build_id 在偏移 0x40，长度 0x20"""
    if len(b) < 0x60 or b[:4] != b"NSO0":
        return None
    return b[0x40:0x60].rstrip(b"\x00").hex()


def pfs0_members(b: bytes):
    """从 PFS0 里取出 (名字, 数据) 列表"""
    if b[:4] != b"PFS0":
        return []
    count, strsz = struct.unpack_from("<II", b, 4)
    str_off = 0x10 + count * 24
    strtab = b[str_off:str_off + strsz]
    data_off = str_off + strsz
    out = []
    for i in range(count):
        do, ds, so, _ = struct.unpack_from("<QQII", b, 0x10 + i * 24)
        end = strtab.find(b"\x00", so)
        name = strtab[so:end].decode(errors="replace")
        out.append((name, b[data_off + do: data_off + do + ds]))
    return out


def scan(path: Path):
    """返回该文件里发现的所有 (来源描述, build_id)"""
    found = []
    try:
        b = path.read_bytes()
    except Exception:
        return found

    bid = nro_build_id(b)
    if bid:
        found.append((path.name, bid))
        return found

    bid = nso_build_id(b)
    if bid:
        found.append((path.name, bid))
        return found

    # PFS0（.nsp）：逐个成员看
    for name, data in pfs0_members(b):
        sub = nso_build_id(data) or nro_build_id(data)
        if sub:
            found.append((f"{path.name}!{name}", sub))
    return found


def main():
    targets = sys.argv[1:] or ["05c838df22834000"]
    targets = [t.lower() for t in targets]

    print(f"目标 build id: {', '.join(targets)}\n")

    all_ids = []
    exts = {".nro", ".ovl", ".nsp", ".kip", ".nca"}
    for p in CARD.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        if "System Volume Information" in str(p):
            continue
        for src, bid in scan(p):
            all_ids.append((src, bid, p))

    print(f"扫描到 {len(all_ids)} 个带 build id 的容器\n")

    hits = []
    for src, bid, p in all_ids:
        for t in targets:
            if bid.startswith(t[:8]) or t.startswith(bid[:8]):
                hits.append((src, bid, p))
                break

    if hits:
        print("=== ★ 命中 ===")
        for src, bid, p in hits:
            print(f"  {bid}")
            print(f"    {src}")
            print(f"    {p}")
    else:
        print("=== 未命中任何模块 ===")
        print("\n卡上所有 build id（前缀 16 位）:")
        for src, bid, p in sorted(all_ids, key=lambda x: x[1]):
            print(f"  {bid[:16]:18} {src}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
