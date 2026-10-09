#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_tls_abi.py — 检查 NRO 是否含 FW 21.0.0 会破坏的旧 TLS 签名

═══════════════════════════════════════════════════════════════════════════
这是什么问题（权威来源）
═══════════════════════════════════════════════════════════════════════════
libnx v4.10.0 之前，用户 TLS 槽从 **+0x108** 开始。而 FW 21.0.0 的内核
把这块区域用于 `thread_cpu_time` —— 于是旧 homebrew 的 TLS 被内核覆写，
表现为各种莫名其妙的崩溃。

修复（libnx commit cad06c006e4e0caf9c63755ac6c2a10a52333e27）:
    把访问从 +0x108 移到 +0x180（真正的用户态区域起点）

签名与新旧字节对照来自 hbpatcher 的 LegacyAbiPatch（alula 逆向），
此处按 nrodoc 的 patterns.rs 逐字节移植:
    https://docs.rs/nrodoc/latest/src/nrodoc/core/patterns.rs.html

═══════════════════════════════════════════════════════════════════════════
为什么这个检查重要
═══════════════════════════════════════════════════════════════════════════
本插件在真机上出现过「Fizeau 未运行时打开 → 整个特斯拉菜单消失」。
TLS 被破坏正是这类"特定条件下才崩"的典型成因 —— 平时不碰 TLS 就没事，
一旦走到某条用到 TLS 的路径就炸。

用 libnx 4.10.0+ 编译的产物不会有 legacy 签名；有的话必须打补丁或重编。
本脚本直接扫产物字节，不需要真机。
═══════════════════════════════════════════════════════════════════════════
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# (标签, legacy 字节, patched 字节) —— 从 nrodoc patterns.rs 移植
# ?? = 通配（打补丁时保留原字节）
SPECS = [
    ("threadTlsGet()",
     "61 D0 3B D5  20 CC 20 8B  00 84 40 F9  C0 03 5F D6",
     "61 D0 3B D5  20 CC 20 8B  00 C0 40 F9  C0 03 5F D6"),
    ("threadTlsSet()",
     "62 D0 3B D5  40 CC 20 8B  01 84 00 F9  C0 03 5F D6",
     "62 D0 3B D5  40 CC 20 8B  01 C0 00 F9  C0 03 5F D6"),
    ("threadEntry() GCC 15 -O2",
     "01 0C 40 F9  A1 FA 00 F9  01 00 00 90  A3 F6 00 F9  B5 22 04 91  21 00 40 F9",
     "01 0C 40 F9  A1 FA 00 F9  01 00 00 90  A3 F6 00 F9  B5 02 06 91  21 00 40 F9"),
    ("threadEntry() GCC 14 -O2",
     "75 D0 3B D5  64 8A 41 A9  A1 82 07 91  A5 E6 01 B9  B5 22 04 91",
     "75 D0 3B D5  64 8A 41 A9  A1 82 07 91  A5 E6 01 B9  B5 02 06 91"),
    ("threadEntry() GCC 13 and below -O2",
     "75 D0 3B D5  A2 E2 01 B9  A5 E6 01 B9  A3 92 1E A9  B5 22 04 91",
     "75 D0 3B D5  A2 E2 01 B9  A5 E6 01 B9  A3 92 1E A9  B5 02 06 91"),
    ("threadEntry() GCC 15 and below -O1",
     "60 02 40 F9  B5 22 04 91  15 10 00 F9  60 02 40 F9  81 22 00 91  01 18 00 F9  "
     "61 02 40 F9  80 06 40 F9  20 14 00 F9",
     "60 02 40 F9  B5 02 06 91  15 10 00 F9  60 02 40 F9  81 22 00 91  01 18 00 F9  "
     "61 02 40 F9  80 06 40 F9  20 14 00 F9"),
    ("threadEntry() LibNX patch 1",
     "84 E2 01 B9  64 0E 40 F9  83 F6 00 F9  63 00 40 B9  42 40 00 D1  84 0A 1F A9  "
     "94 22 04 91  83 DE 00 B9",
     "84 E2 01 B9  64 0E 40 F9  83 F6 00 F9  63 00 40 B9  42 40 00 D1  84 0A 1F A9  "
     "94 02 06 91  83 DE 00 B9"),
    ("threadEntry() LibNX patch 2",
     "02 02 80 D2  F3 53 01 A9  F3 03 00 AA  74 D0 3B D5  94 22 04 91  03 00 40 F9  "
     "F5 13 00 F9  81 DA 00 B9  01 0C 40 F9  83 72 00 F9  81 76 00 F9  ?? ?? ?? ??  "
     "?? ?? ?? ??  21 00 40 F9  3F 40 00 F1  21 20 82 9A  02 10 40 F9  ?? ?? ?? ??  "
     "?? ?? ?? ??  41 00 01 CB  81 7A 00 F9  61 00 40 B9  81 DE 00 B9",
     "02 02 80 D2  F3 53 01 A9  F3 03 00 AA  74 D0 3B D5  94 02 06 91  03 00 40 F9  "
     "F5 13 00 F9  81 62 00 B9  01 0C 40 F9  83 36 00 F9  81 3A 00 F9  ?? ?? ?? ??  "
     "?? ?? ?? ??  21 00 40 F9  3F 40 00 F1  21 20 82 9A  02 10 40 F9  ?? ?? ?? ??  "
     "?? ?? ?? ??  41 00 01 CB  81 3E 00 F9  61 00 40 B9  81 66 00 B9"),
]


def parse_spec(spec: str):
    """'61 D0 ?' -> (bytes, mask)，mask 中 False 表示通配"""
    toks = spec.replace("\n", " ").split()
    data = bytearray()
    mask = bytearray()
    for t in toks:
        if t == "??":
            data.append(0)
            mask.append(0)
        else:
            data.append(int(t, 16))
            mask.append(1)
    return bytes(data), bytes(mask)


def find_all(hay: bytes, needle: bytes, mask: bytes):
    """在 hay 里找所有匹配（支持通配），返回偏移列表"""
    n = len(needle)
    out = []
    i = 0
    fixed = [k for k in range(n) if mask[k]]
    if not fixed:
        return out
    # 用第一个固定字节做快速筛选
    anchor = fixed[0]
    a_byte = needle[anchor]
    while True:
        j = hay.find(bytes([a_byte]), i)
        if j < 0:
            break
        start = j - anchor
        i = j + 1
        if start < 0 or start + n > len(hay):
            continue
        if all(hay[start + k] == needle[k] for k in fixed):
            out.append(start)
    return out


def nro_text_range(b: bytes):
    """读 NRO 头里的 .text 段范围（偏移 0x10 魔数，0x20 段表）"""
    if len(b) < 0x40 or b[0x10:0x14] != b"NRO0":
        return None
    # NRO 头: 0x10 magic, 0x14 version, 0x18 size, 0x1C flags(8), 0x24 text{off,size}, ...
    import struct
    text_off, text_size = struct.unpack_from("<II", b, 0x24)
    return text_off, text_size


def main():
    paths = sys.argv[1:]
    if not paths:
        root = Path(__file__).resolve().parent.parent
        paths = [str(root / "overlay" / "FilterNX.ovl"),
                 str(root / "dist" / "switch" / ".overlays" / "Chaoneng.ovl")]

    print("=== TLS ABI 检查（FW 21.0.0+ 会破坏旧签名）===\n")
    print("  背景: libnx < 4.10.0 的用户 TLS 从 +0x108 开始，")
    print("        而 FW 21.0.0 内核把该区域用于 thread_cpu_time → TLS 被覆写")
    print("        修复: 移到 +0x180\n")

    any_legacy = False
    any_patched = False

    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"  [跳过] {path}（不存在）")
            continue

        b = path.read_bytes()
        tr = nro_text_range(b)
        print(f"  {path.name}  ({len(b)} 字节)")
        if tr is None:
            print("         ★ 不是合法 NRO（找不到 NRO0 魔数）")
            continue
        text_off, text_size = tr
        text = b[text_off:text_off + text_size]
        print(f"        .text: 偏移 0x{text_off:X}  大小 {text_size} 字节")

        legacy_hits = []
        patched_hits = []
        for label, leg, pat in SPECS:
            lb, lm = parse_spec(leg)
            pb, pm = parse_spec(pat)
            for off in find_all(text, lb, lm):
                legacy_hits.append((label, off))
            for off in find_all(text, pb, pm):
                patched_hits.append((label, off))

        if legacy_hits:
            any_legacy = True
            print(f"        ★★ 发现 {len(legacy_hits)} 处**旧 TLS 签名**！")
            for label, off in legacy_hits[:10]:
                print(f"             {label}  @ .text+0x{off:X}")
            print("             → 在 FW 21.0.0+ 上 TLS 会被内核破坏，必须重编或打补丁")
        else:
            print("        ✓ 没有旧 TLS 签名")

        if patched_hits:
            any_patched = True
            print(f"        （发现 {len(patched_hits)} 处**已修补**签名 —— 有人打过补丁）")
        print()

    print("=" * 62)
    if any_legacy:
        print("结果: ★ 产物含旧 TLS 签名 —— 这正是 FW 21.0.0+ 上崩溃的已知成因")
        print("      处理: 用 libnx >= 4.10.0 重新编译（本项目用 4.12.0，应已正确）")
        return 1
    if any_patched:
        print("结果: 产物已被打过 TLS 补丁（ABI 正确）")
        return 0
    print("结果: 产物不含旧 TLS 签名（libnx >= 4.10.0 编译，ABI 正确）")
    print("      排除「TLS ABI 破坏」这个成因。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
