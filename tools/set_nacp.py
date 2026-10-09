#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
set_nacp.py — 改写 NRO 里 NACP 的应用名、发行商与版本（UTF-8）

═══════════════════════════════════════════════════════════════════════════
⚠ 字段偏移必须精确（这里踩过一次坑）
═══════════════════════════════════════════════════════════════════════════
NACP（ApplicationControlProperty）的布局由 libnx switch/nacp.h 定义:

    typedef struct { char name[0x200]; char author[0x100]; } NacpLanguageEntry;
                                                      // ↑ 0x300 字节/语言

    typedef struct {
        NacpLanguageEntryData lang_data;   // 0x0000 .. 0x2FFF  (16 × 0x300)
        u8 isbn[0x25];                     // 0x3000
        u8 startup_user_account;           // 0x3025
        u8 user_account_switch_lock;       // 0x3026
        u8 add_on_content_registration_type; // 0x3027
        u32 attribute_flag;                // 0x3028
        u32 supported_language_flag;       // 0x302C
        u32 parental_control_flag;         // 0x3030
        u8 screenshot/video_capture/...;   // 0x3034..0x3037
        u64 presence_group_id;             // 0x3038
        s8 rating_age[0x20];               // 0x3040
        char display_version[0x10];        // 0x3060  ← 版本在这里！
        ...
    } ApplicationControlProperty;

这些偏移是由 tools/nacp_offsets.c 用编译器实测出来的，不是手算。

**曾经犯的错**: 把 display_version 当成 0x3000，结果版本被写进了 isbn 字段。
菜单读的是 display_version（0x3060），所以版本一直显示旧值 —— 而且
read_nacp.py 也在读 0x3000，于是"回读校验通过"是假通过，两边错得一致。

**另一个错**: 以为 lang 步长是 0x200（那是 name 的大小）。实际步长 0x300，
author 在每个语言项内 +0x200 处。

═══════════════════════════════════════════════════════════════════════════
为什么不用 nacptool 传参
═══════════════════════════════════════════════════════════════════════════
nacptool 在 Windows 下按**系统 ANSI 代码页**编码参数，中文会变成 GBK:

    传入 "超能滤镜"  →  写入 b3 ac c4 dc c2 cb be b5   (GBK)
    正确的 UTF-8     →  e8 b6 85 e8 83 bd e6 bb a4 e9 95 9c

而 NACP 约定 UTF-8。所以流程是: nacptool 先造结构 → 本脚本直接改写字节。

═══════════════════════════════════════════════════════════════════════════
Ultrahand / Tesla 读的是哪个字段（源码依据）
═══════════════════════════════════════════════════════════════════════════
Ultrahand-Overlay source/utils.hpp:1043-1052  getOverlayInfo():
    memchr(nacp.lang_data.lang[0].name, '\0', ...)   → 名字（语言槽 0）
    memchr(nacp.display_version, '\0', ...)          → 版本
再经 source/main.cpp:6894-6898 被 overlays.ini 的 custom_name/custom_version 覆盖。
"""

import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 偏移常量（由 tools/nacp_offsets.c 用编译器实测）──
LANG_STRIDE   = 0x300   # NacpLanguageEntry 大小
NAME_OFF      = 0x000   # 每个语言项内 name 的偏移
NAME_SIZE     = 0x200
AUTHOR_OFF    = 0x200   # 每个语言项内 author 的偏移
AUTHOR_SIZE   = 0x100
VER_OFF       = 0x3060  # display_version —— 真正的版本字段
VER_SIZE      = 0x10
ISBN_OFF      = 0x3000  # isbn —— 曾经误当作版本字段
ISBN_SIZE     = 0x25

LANG_COUNT = 16


def find_nacp(b: bytes):
    """定位 NACP 在文件中的绝对偏移。

    NRO 资源段以 "ASET" 开头:
        magic[4] version[4] 然后三个 (u64 offset, u64 size) = icon, nacp, romfs
    offset 相对 ASET 起点。
    """
    idx = b.find(b"ASET")
    if idx < 0:
        return None
    nacp_off, nacp_size = struct.unpack_from("<QQ", b, idx + 8 + 16)
    if nacp_size == 0:
        return None
    return idx + nacp_off


def read_cstr(field: bytes) -> str:
    nul = field.find(b"\x00")
    if nul >= 0:
        field = field[:nul]
    try:
        return field.decode("utf-8")
    except Exception:
        return f"<非 UTF-8> {field[:16].hex()}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv

    if len(args) < 2:
        print(__doc__)
        print("用法: set_nacp.py <nro文件> <名称> [版本] [--dry-run]")
        return 1

    path = Path(args[0])
    name = args[1]
    version = args[2] if len(args) > 2 else None

    if not path.is_file():
        print(f"not found: {path}")
        return 1

    enc_name = name.encode("utf-8")
    if len(enc_name) >= NAME_SIZE:
        print(f"[FAIL] name too long: {len(enc_name)} bytes, max {NAME_SIZE - 1}")
        return 1

    enc_ver = version.encode("utf-8") if version else None
    if enc_ver and len(enc_ver) >= VER_SIZE:
        print(f"[FAIL] version too long: {len(enc_ver)} bytes, max {VER_SIZE - 1}")
        return 1

    b = bytearray(path.read_bytes())
    off = find_nacp(b)
    if off is None:
        print("[FAIL] NACP not found (asset section missing)")
        return 1

    print("=== set NACP fields ===")
    print(f"  file: {path.name}")
    print(f"  NACP: offset 0x{off:X}")
    print(f"  name: {name!r}")
    print(f"        UTF-8 {' '.join(f'{x:02x}' for x in enc_name)}")
    if enc_ver:
        print(f"  vers: {version!r} @ NACP+0x{VER_OFF:X} (display_version)")

    # ── 1. 逐语言写入 name 与 author ──
    # 菜单只读 lang[0]，但写全 16 个槽位更稳妥（不依赖菜单读哪个槽）。
    for i in range(LANG_COUNT):
        base_n = off + i * LANG_STRIDE + NAME_OFF
        b[base_n:base_n + NAME_SIZE] = b"\x00" * NAME_SIZE
        b[base_n:base_n + len(enc_name)] = enc_name

        base_a = off + i * LANG_STRIDE + AUTHOR_OFF
        b[base_a:base_a + AUTHOR_SIZE] = b"\x00" * AUTHOR_SIZE
        b[base_a:base_a + len(enc_name)] = enc_name

    # ── 2. display_version（真正的版本字段）──
    if enc_ver:
        base_v = off + VER_OFF
        b[base_v:base_v + VER_SIZE] = b"\x00" * VER_SIZE
        b[base_v:base_v + len(enc_ver)] = enc_ver

    # ── 3. 清空 isbn ──
    # 早期版本把版本号误写到这里，残留会让 NACP 元数据不一致。清掉。
    base_i = off + ISBN_OFF
    b[base_i:base_i + ISBN_SIZE] = b"\x00" * ISBN_SIZE

    if dry:
        print("  (--dry-run, file not modified)")
        return 0

    path.write_bytes(bytes(b))
    print(f"  [OK] wrote name/author to {LANG_COUNT} slots"
          + (", display_version, cleared isbn" if enc_ver else ""))

    # ── 4. 回读校验（读的是与写入相同的偏移，但独立代码路径）──
    check = path.read_bytes()
    coff = find_nacp(check)
    bad = 0

    for i in range(LANG_COUNT):
        got = check[coff + i * LANG_STRIDE + NAME_OFF:
                    coff + i * LANG_STRIDE + NAME_OFF + NAME_SIZE].split(b"\x00")[0]
        if got != enc_name:
            print(f"  [FAIL] name slot {i} mismatch: {read_cstr(got)!r}")
            bad += 1

    if enc_ver:
        got_v = check[coff + VER_OFF: coff + VER_OFF + VER_SIZE].split(b"\x00")[0]
        if got_v != enc_ver:
            print(f"  [FAIL] display_version mismatch: {got_v!r} != {enc_ver!r}")
            bad += 1
        else:
            print(f"  [OK] display_version = {got_v.decode()!r}")

    if bad:
        print(f"\n[FAIL] read-back mismatch in {bad} place(s)")
        return 1

    print("  [OK] read-back verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
