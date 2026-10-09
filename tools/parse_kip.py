#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_kip.py — 解析 KIP1 文件结构，定位其参数表

KIP1 头部（偏移 0x00，共 0x100 字节）:
    0x00  magic "KIP1"
    0x04  name[12]        ("Loader")
    0x10  u32 version
    0x14  u32 priority
    0x18  u32 stack_size
    0x1C  u32 thread_stack_size  (或有差异)
    0x20  u32 text_size
    0x24  u32 rodata_size
    0x28  u32 data_size
    0x2C  u32 bss_size
    ...
    0x100 起为各段数据

KipTool 的 "Kip Wizard" 用 CustomizeTable + "CUST" 模式定位可调参数，
因此本脚本重点是在文件里找 "CUST" 模式与参数表结构。
"""

import struct
import sys
from pathlib import Path

KIP_HEADER_SIZE = 0x100


def ascii_strings(data, min_len=4):
    out = []
    cur = bytearray()
    start = 0
    for i, b in enumerate(data):
        if 32 <= b < 127:
            if not cur:
                start = i
            cur.append(b)
        else:
            if len(cur) >= min_len:
                out.append((start, cur.decode()))
            cur.clear()
    if len(cur) >= min_len:
        out.append((start, cur.decode()))
    return out


def main():
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\hnayz\Desktop\loader.kip")
    if not p.is_file():
        print(f"找不到 {p}")
        return 1

    b = p.read_bytes()
    print(f"=== {p.name}  ({len(b):,} 字节) ===\n")

    if b[:4] != b"KIP1":
        print(f"★ 不是 KIP1（magic = {b[:4]}）")
        return 1
    print(f"  magic = {b[:4]}")

    # ---- KIP1 头 ----
    name = b[4:16].rstrip(b"\x00").decode(errors="replace")
    print(f"  name  = {name}")

    # 逐字段打印 u32，便于人工核对（不同 KIP 版本字段顺序略有差异）
    print("\n  头部 u32 字段:")
    for off in range(0x10, 0x40, 4):
        v = struct.unpack_from("<I", b, off)[0]
        print(f"    0x{off:02X}  0x{v:08X}  ({v:,})")

    # ---- 段布局推断 ----
    # 常见布局: 0x20 text_size, 0x24 rodata_size, 0x28 data_size, 0x2C bss_size
    text_size   = struct.unpack_from("<I", b, 0x20)[0]
    rodata_size = struct.unpack_from("<I", b, 0x24)[0]
    data_size   = struct.unpack_from("<I", b, 0x28)[0]
    bss_size    = struct.unpack_from("<I", b, 0x2C)[0]
    total = text_size + rodata_size + data_size
    print(f"\n  段尺寸推断:")
    print(f"    text  = {text_size:,}")
    print(f"    rodata= {rodata_size:,}")
    print(f"    data  = {data_size:,}")
    print(f"    bss   = {bss_size:,}")
    print(f"    合计  = {total:,}  + 头 0x100 = {total + KIP_HEADER_SIZE:,}")
    print(f"    文件  = {len(b):,}   {'✓ 吻合' if total + KIP_HEADER_SIZE == len(b) else '★ 不吻合（字段顺序需调整）'}")

    # ---- 找 "CUST" 模式（KipTool 的标记）----
    print("\n  查找 KipTool 的 CUST 标记:")
    for magic in (b"CUST", b"CustomizeTable", b"Kip tool", b"KipTool", b"KT\x00"):
        idx = b.find(magic)
        print(f"    {magic!r:20} -> {'@ 0x%X' % idx if idx >= 0 else '未找到'}")

    # ---- 所有可读字符串 ----
    print("\n  可读字符串（长度>=6，最多 80 条）:")
    strs = ascii_strings(b, 6)
    print(f"    共 {len(strs)} 条")
    for off, s in strs[:80]:
        print(f"      0x{off:06X}  {s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
