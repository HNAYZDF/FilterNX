#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
read_nacp.py — 读取 NRO 里 NACP 的元数据（名字 / 发行商 / 版本）

═══════════════════════════════════════════════════════════════════════════
⚠ 偏移必须精确（这里踩过坑）
═══════════════════════════════════════════════════════════════════════════
布局由 libnx switch/nacp.h 定义，偏移由 tools/nacp_offsets.c 用编译器实测:

    NacpLanguageEntry = { char name[0x200]; char author[0x100]; }   // 0x300/语言
        lang[i].name   = i*0x300 + 0x000
        lang[i].author = i*0x300 + 0x200     ← 发行商在这里（不是 0x2000！）
    isbn            = 0x3000
    display_version = 0x3060                 ← 版本在这里（不是 0x3000！）

**曾经犯的两个错**:
  1. 把 display_version 当成 0x3000（那是 isbn），于是版本写错、也读错，
     回读校验"通过"是假通过 —— 两边错得一致。
  2. 以为 lang 步长 0x200（那是 name 的大小），把发行商标在了 0x2000。

本脚本用 set_nacp.py 里同一组常量，避免两处再次不一致。
"""

import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LANG_STRIDE = 0x300
NAME_OFF    = 0x000
NAME_SIZE   = 0x200
AUTHOR_OFF  = 0x200
AUTHOR_SIZE = 0x100
VER_OFF     = 0x3060
VER_SIZE    = 0x10
ISBN_OFF    = 0x3000
ISBN_SIZE   = 0x25

LANGS = [
    "AmericanEnglish", "BritishEnglish", "Japanese", "French",
    "German", "LatinAmericanSpanish", "Spanish", "Italian",
    "Dutch", "CanadianFrench", "Portuguese", "Russian",
    "Korean", "TraditionalChinese", "SimplifiedChinese", "Reserved",
]


def find_nacp(b: bytes):
    """返回 (NACP 绝对偏移, ASET 起点, 资源段三元组)"""
    idx = b.find(b"ASET")
    if idx < 0:
        return None, None, None
    sections = []
    for i in range(3):
        o, s = struct.unpack_from("<QQ", b, idx + 8 + i * 16)
        sections.append((o, s))
    nacp_off, nacp_size = sections[1]
    if nacp_size == 0:
        return None, idx, sections
    return idx + nacp_off, idx, sections


def cstr(raw: bytes) -> str:
    nul = raw.find(b"\x00")
    if nul >= 0:
        raw = raw[:nul]
    try:
        return raw.decode("utf-8")
    except Exception:
        return f"<非 UTF-8: {raw[:16].hex()}>"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"找不到 {p}")
        return 1

    b = p.read_bytes()
    print(f"=== {p.name}  ({len(b):,} 字节) ===\n")

    off, aset, sections = find_nacp(b)
    if sections:
        print("  资源段 ASET:")
        for i, (o, s) in enumerate(sections):
            print(f"    {['icon','nacp','romfs'][i]:6} 偏移 0x{o:X}  大小 {s:,}")
        print()

    if off is None:
        print("  [FAIL] 未找到 NACP")
        return 1

    print(f"  NACP 绝对偏移 0x{off:X}\n")

    # ── 应用名称（lang[i].name）──
    print("  ── 应用名称（lang[i].name，菜单读的是 [0]）──")
    nonempty = 0
    for i, lang in enumerate(LANGS):
        s = cstr(b[off + i * LANG_STRIDE + NAME_OFF:
                    off + i * LANG_STRIDE + NAME_OFF + NAME_SIZE])
        if s:
            nonempty += 1
            print(f"    [{i:2}] {lang:20} {s!r}")
    if nonempty == 0:
        print("    （全部为空）")

    # ── 发行商（lang[i].author）──
    print("\n  ── 发行商（lang[i].author，位于每个语言项内 +0x200）──")
    nonempty = 0
    for i, lang in enumerate(LANGS):
        s = cstr(b[off + i * LANG_STRIDE + AUTHOR_OFF:
                    off + i * LANG_STRIDE + AUTHOR_OFF + AUTHOR_SIZE])
        if s:
            nonempty += 1
            print(f"    [{i:2}] {lang:20} {s!r}")
    if nonempty == 0:
        print("    （全部为空）")

    # ── 版本（display_version @ 0x3060）──
    print(f"\n  ── 版本（display_version @ NACP+0x{VER_OFF:X}）──")
    ver = cstr(b[off + VER_OFF: off + VER_OFF + VER_SIZE])
    print(f"    {ver!r}" + ("   ← 为空！" if not ver else ""))

    # ── isbn（曾经被误写的地方，检查是否有残留）──
    isbn = cstr(b[off + ISBN_OFF: off + ISBN_OFF + ISBN_SIZE])
    if isbn:
        print(f"\n  ⚠ isbn @ 0x{ISBN_OFF:X} 有内容: {isbn!r}")
        print("     （早期版本把版本号误写到这里；正常应为空）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
