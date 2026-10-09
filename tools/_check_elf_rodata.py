#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_check_elf_rodata.py — 在 ELF 的真实 .rodata 段里搜服务名

用 readelf 得到的段表（硬编码不了，这里重新解析 ELF 头）：
    .rodata  offset 0x991C0  size 0x8538   flags A
如果 fizeau 不在这个范围内，说明它没被分配进可加载段 ——
那 NRO 里没有它就是正常的，问题在编译期而非转换期。
"""

import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ELF = Path("filternx/overlay/build/FilterNX.elf")
b = ELF.read_bytes()

# ── 解析 ELF64 段表 ──
assert b[:4] == b"\x7fELF", "不是 ELF"
is64 = b[4] == 2
e_shoff = struct.unpack_from("<Q", b, 0x28)[0]
e_shentsize = struct.unpack_from("<H", b, 0x3A)[0]
e_shnum = struct.unpack_from("<H", b, 0x3C)[0]
e_shstrndx = struct.unpack_from("<H", b, 0x3E)[0]

def sh(i):
    o = e_shoff + i * e_shentsize
    name, typ, flags, addr, off, size = struct.unpack_from("<IIQQQQ", b, o)
    return {"name_off": name, "type": typ, "flags": flags,
            "addr": addr, "offset": off, "size": size}

shstr = sh(e_shstrndx)
def shname(noff):
    a = shstr["offset"] + noff
    z = b.find(b"\x00", a)
    return b[a:z].decode("ascii", "replace")

print(f"=== {ELF.name}  ({len(b):,} 字节) ===")
print(f"  段数 {e_shnum}")
print()

target_needle = b"fizeau"
found_any = False
for i in range(e_shnum):
    s = sh(i)
    nm = shname(s["name_off"])
    seg = b[s["offset"]:s["offset"] + s["size"]]
    hit = seg.find(target_needle)
    alloc = "A" if (s["flags"] & 0x2) else "-"
    mark = ""
    if hit >= 0:
        found_any = True
        mark = f"   ← fizeau @ 段内 0x{hit:X}"
    if nm in (".text", ".rodata", ".data", ".data.rel.ro", ".strtab",
              ".symtab", ".shstrtab", ".debug_str") or hit >= 0:
        print(f"  [{i:2}] {nm:18} flags={alloc} off=0x{s['offset']:08X} "
              f"size={s['size']:>9,}{mark}")

print()
print(f"  结论: fizeau {'存在于某个段' if found_any else '不在任何段里'}")
if found_any:
    # 找出在哪个段
    for i in range(e_shnum):
        s = sh(i)
        seg = b[s["offset"]:s["offset"] + s["size"]]
        if seg.find(target_needle) >= 0:
            alloc = "可加载" if (s["flags"] & 0x2) else "非可加载"
            print(f"        -> 在 {shname(s['name_off'])}（{alloc}）")
