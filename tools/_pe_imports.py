#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 PE 的导入表，列出 exe 依赖的 DLL。"""

import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

p = Path(sys.argv[1] if len(sys.argv) > 1 else
         "filternx/tests/build/test_presets.exe")
b = p.read_bytes()

# ── DOS 头 → PE 头 ──
e_lfanew = struct.unpack_from("<I", b, 0x3C)[0]
assert b[e_lfanew:e_lfanew + 4] == b"PE\0\0", "不是 PE"
coff = e_lfanew + 4
num_sec, = struct.unpack_from("<H", b, coff + 2)
opt_size, = struct.unpack_from("<H", b, coff + 16)
opt = coff + 20
magic, = struct.unpack_from("<H", b, opt)
pe32p = magic == 0x20B
# 数据目录: PE32+ 从 opt+112 开始；导入表是第 2 项
dd = opt + (112 if pe32p else 96)
imp_rva, imp_size = struct.unpack_from("<II", b, dd + 8)

secs = []
for i in range(num_sec):
    o = opt + opt_size + i * 40
    name = b[o:o + 8].rstrip(b"\x00").decode("ascii", "replace")
    vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", b, o + 8)
    secs.append((name, vaddr, vsize, raw, rsize))


def rva2off(rva):
    for name, va, vs, raw, rs in secs:
        if va <= rva < va + max(vs, rs):
            return raw + (rva - va)
    return None


print(f"=== {p.name} ===")
print(f"  PE{'+' if pe32p else ''}  段数 {num_sec}")
print(f"  导入表 RVA 0x{imp_rva:X}  大小 {imp_size}")
print()
print("  依赖的 DLL:")
o = rva2off(imp_rva)
if o is None:
    print("    （读不到导入表）")
else:
    k = 0
    while True:
        ent = o + k * 20
        name_rva, = struct.unpack_from("<I", b, ent + 12)
        if name_rva == 0:
            break
        no = rva2off(name_rva)
        if no is None:
            break
        z = b.find(b"\x00", no)
        dll = b[no:z].decode("ascii", "replace")
        print(f"    {dll}")
        k += 1
        if k > 40:
            break
