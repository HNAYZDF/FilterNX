#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_dig_service_name.py — 深挖「服务名字符串去哪了」

NRO 头的段表存的是**相对 .text 基址的偏移**，不是文件绝对偏移。
第一版审计脚本按绝对偏移解析，于是搜索范围全错。
本脚本用正确解析，在真实范围内搜服务名。
"""

import re
import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

p = Path("filternx/overlay/FilterNX.ovl")
b = p.read_bytes()

# NRO 头: 0x10 magic, 0x14 version, 0x18 size, 0x1C flags(8),
#         0x24 text{u32 off,u32 size}, 0x2C ro{u32 off,u32 size},
#         0x34 data{u32 off,u32 size}, 0x3C bss_size
t_off, t_sz = struct.unpack_from("<II", b, 0x24)
r_off, r_sz = struct.unpack_from("<II", b, 0x2C)
d_off, d_sz = struct.unpack_from("<II", b, 0x34)
bss = struct.unpack_from("<I", b, 0x3C)[0]

print(f"=== {p.name}  ({len(b):,} 字节) ===")
print(f"  NRO 头里的段表（相对 .text 基址 = 0x{t_off:X}）")
print(f"    text   相对 0x{t_off:X}  大小 {t_sz:,}")
print(f"    rodata 相对 0x{r_off:X}  大小 {r_sz:,}")
print(f"    data   相对 0x{d_off:X}  大小 {d_sz:,}")
print(f"    bss    {bss:,}")
print()

# 真实文件范围
sections = {
    "text":   (t_off, t_off + t_sz),
    "rodata": (t_off + r_off, t_off + r_off + r_sz),
    "data":   (t_off + d_off, t_off + d_off + d_sz),
}
print("  真实文件范围:")
for n, (a, z) in sections.items():
    print(f"    {n:8} 0x{a:X} .. 0x{z:X}")
print()

# 在全部范围内搜
print("  搜 'fizeau':")
for n, (a, z) in sections.items():
    i = b.find(b"fizeau", a, z)
    print(f"    {n:8} {'0x%X' % i if i >= 0 else '未找到'}")
i = b.find(b"fizeau")
print(f"    全文件   {'0x%X' % i if i >= 0 else '未找到'}")
print()

# 列出 rodata 里所有可打印串（正确的范围）
ro_a, ro_z = sections["rodata"]
ro = b[ro_a:ro_z]
print(f"  rodata ({len(ro):,} 字节) 里的 ASCII 串（长度 >= 4）:")
seen = []
for m in re.finditer(rb'[ -~]{4,48}', ro):
    s = m.group(0)
    if s not in seen:
        seen.append(s)
print(f"    共 {len(seen)} 个不同的串，列出全部:")
for s in seen:
    print(f"      {s.decode('ascii', 'replace')!r}")
