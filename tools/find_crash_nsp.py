#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_crash_nsp.py — 把崩溃报告的 build id 与卡上所有 sysmodule 匹配

重点: 之前只扫了 .nro/.ovl，漏掉了 atmosphere/contents/*/exefs.nsp 里的
sysmodule（它们内部是 NSO，build_id 在 PFS0 成员里）。
"""

import struct
import sys
from pathlib import Path

CARD = Path("G:/")
TARGET = sys.argv[1] if len(sys.argv) > 1 else "05c838df22834000"


def pfs0_members(b: bytes):
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
        out.append((strtab[so:end].decode(errors="replace"),
                    b[data_off + do: data_off + do + ds]))
    return out


def nso_bid(b: bytes):
    if len(b) < 0x60 or b[:4] != b"NSO0":
        return None
    return b[0x40:0x60].rstrip(b"\x00").hex()


def nro_bid(b: bytes):
    if len(b) < 0x58 or b[0x10:0x14] != b"NRO0":
        return None
    return b[0x38:0x58].rstrip(b"\x00").hex()


def main():
    print(f"目标 build id: {TARGET}\n")
    print("=== atmosphere/contents 下所有 sysmodule ===")
    hits = []
    for d in sorted((CARD / "atmosphere" / "contents").iterdir()):
        if not d.is_dir():
            continue
        nsp = d / "exefs.nsp"
        if not nsp.is_file():
            print(f"  {d.name:22} (无 exefs.nsp)")
            continue
        b = nsp.read_bytes()
        members = pfs0_members(b)
        if not members:
            # 可能是裸 NSO
            bid = nso_bid(b)
            print(f"  {d.name:22} 裸NSO/kernel? magic={b[:4]} bid={bid}")
            if bid and bid.startswith(TARGET[:8]):
                hits.append((d.name, bid))
            continue
        line = f"  {d.name:22} PFS0[{len(members)}]"
        for name, data in members:
            bid = nso_bid(data)
            if bid:
                mark = ""
                if bid.startswith(TARGET[:8]) or TARGET.startswith(bid[:8]):
                    mark = "  <<< ★命中"
                    hits.append((d.name, bid))
                line += f"\n      {name:12} {bid}{mark}"
        print(line)

    print()
    if hits:
        print("=== ★ 崩溃报告匹配到: ===")
        for n, bid in hits:
            print(f"  {n}  build_id={bid}")
    else:
        print("=== 未匹配到任何 sysmodule ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
