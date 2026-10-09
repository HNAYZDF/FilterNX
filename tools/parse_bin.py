#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_bin.py — 完整解析 Atmosphère 的 thread_info.bin 崩溃转储

不做假设，把 1416 字节全部结构化展示，找出进程/线程/寄存器信息。
"""

import struct
import sys
from pathlib import Path

p = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not p or not p.is_file():
    print("用法: parse_bin.py <thread_info.bin>")
    sys.exit(1)

b = p.read_bytes()
print(f"=== {p.name}  ({len(b)} 字节) ===\n")

# 头部：magic + 一系列 u32/u64
print("--- 前 0x60 字节按 u32 解释 ---")
for i in range(0, 0x60, 4):
    v = struct.unpack_from("<I", b, i)[0]
    q = struct.unpack_from("<Q", b, i)[0] if i + 8 <= len(b) else 0
    print(f"  0x{i:03X}  u32=0x{v:08X} ({v:>12})   u64=0x{q:016X}")

print("\n--- 全部非零的 8 字节对齐值（疑似指针/地址）---")
seen = set()
for i in range(0, len(b) - 8, 8):
    q = struct.unpack_from("<Q", b, i)[0]
    if q == 0:
        continue
    # 只看像地址的（0x1000 ~ 0x8000000000）
    if 0x1000 <= q <= 0x8000000000:
        if q in seen:
            continue
        seen.add(q)
        print(f"  0x{i:04X}  0x{q:012X}")

print("\n--- 可读 ASCII 串 ---")
cur = bytearray()
for i, byte in enumerate(b):
    if 32 <= byte < 127:
        cur.append(byte)
    else:
        if len(cur) >= 5:
            print(f"  0x{i - len(cur):04X}  {cur.decode()}")
        cur.clear()
if len(cur) >= 5:
    print(f"  0x{len(b) - len(cur):04X}  {cur.decode()}")

# DTI2 之后的调试配置区
print("\n--- DTI2 结构区（0x00~0x20）字段猜测 ---")
magic = b[0:4]
size1 = struct.unpack_from("<I", b, 4)[0]
size2 = struct.unpack_from("<I", b, 8)[0]
print(f"  magic   = {magic}")
print(f"  0x04    = 0x{size1:X} ({size1})")
print(f"  0x08    = 0x{size2:X} ({size2})")
print(f"  0x0C    = 0x{struct.unpack_from('<I', b, 0xC)[0]:X}")
print(f"  0x20    = 0x{struct.unpack_from('<Q', b, 0x20)[0]:X}")
print(f"  0x28    = 0x{struct.unpack_from('<Q', b, 0x28)[0]:X}")
print(f"  0x30    = 0x{struct.unpack_from('<Q', b, 0x30)[0]:X}")
print(f"  0x38    = 0x{struct.unpack_from('<Q', b, 0x38)[0]:X}")
print(f"  0x40    = 0x{struct.unpack_from('<Q', b, 0x40)[0]:X}")
print(f"  0x48    = 0x{struct.unpack_from('<Q', b, 0x48)[0]:X}")
