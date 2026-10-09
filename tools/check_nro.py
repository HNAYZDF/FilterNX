#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_nro.py — 严格校验 NRO 头部，复刻 nx-ovlloader 的检验逻辑

动机: nx-ovlloader 2.0.2 的 loadNro() 会做这些检查，任一失败就
fatalThrow —— 表现为"整个特斯拉崩掉"：

    header = (NroHeader*)(nrobuf + sizeof(NroStart));   // 偏移 0x10
    if (header->magic != NROHEADER_MAGIC) fatalThrow(5);
    for i in 0..3:
        if (segments[i].file_off >= header->size) fatalThrow(6);
        if (segments[i].size > header->size - segments[i].file_off) fatalThrow(6);

另外还有一条隐含约束: 整个文件必须能一次读进 applet heap
（HOS 21+ 默认 4MB、20+ 6MB、更早 8MB），否则读不完整。

本脚本按上述规则校验任意 .ovl / .nro，并与已知可用的参照对比。
"""

import struct
import sys
from pathlib import Path

NROHEADER_MAGIC = 0x304F524E
NROSTART_SIZE = 0x10
NROHEADER_OFF = NROSTART_SIZE           # nx-ovlloader 用的偏移

# 默认 heap（HOS 21.0.0+）—— 文件必须小于它才能被完整读入
HEAP_DEFAULT = 4 * 1024 * 1024


def check(path: Path):
    b = path.read_bytes()
    size = len(b)

    print(f"=== {path.name}  ({size:,} 字节) ===")

    if size < NROHEADER_OFF + 0x38:
        print("  ★ 文件太小，装不下 NRO 头")
        return False

    # ---- NroStart ----
    (unused, mod_offset) = struct.unpack_from("<II", b, 0)
    print(f"  [NroStart @0x00]  unused=0x{unused:08X}  mod_offset=0x{mod_offset:X}")

    # ---- NroHeader @0x10（这是 nx-ovlloader 解析的位置）----
    off = NROHEADER_OFF
    (magic, unk1, hsize, unk2) = struct.unpack_from("<IIII", b, off)
    magic_raw = b[off:off + 4]

    ok = True
    if magic == NROHEADER_MAGIC:
        print(f"  [NroHeader @0x10] magic = {magic_raw} (0x{magic:08X})  ✓ 正确")
    else:
        print(f"  [NroHeader @0x10] magic = {magic_raw} (0x{magic:08X})  ★ 错误！"
              f" 应为 {struct.pack('<I', NROHEADER_MAGIC)}")
        print("     -> nx-ovlloader 会 fatalThrow(5)，特斯拉会崩")
        ok = False

    print(f"                    header->size = {hsize:,} (0x{hsize:X})")
    print(f"                    unk1=0x{unk1:X} unk2=0x{unk2:X}")

    # ---- 分段 ----
    segs = []
    for i in range(3):
        fo, sz = struct.unpack_from("<II", b, off + 0x10 + i * 8)
        segs.append((fo, sz))
    bss_size, unk3 = struct.unpack_from("<II", b, off + 0x28)

    names = [".text", ".rodata", ".data"]
    print(f"  [分段] " + "  ".join(f"{names[i]}: off=0x{segs[i][0]:X} size=0x{segs[i][1]:X}"
                                   for i in range(3)))
    print(f"         bss_size=0x{bss_size:X}")

    # 复刻 nx-ovlloader 的校验
    for i in range(3):
        fo, sz = segs[i]
        if fo >= hsize:
            print(f"  ★ fatalThrow(6): {names[i]} file_off 0x{fo:X} >= header->size 0x{hsize:X}")
            ok = False
        elif sz > hsize - fo:
            print(f"  ★ fatalThrow(6): {names[i]} size 0x{sz:X} > "
                  f"(size - off) 0x{hsize - fo:X}")
            ok = False

    if ok:
        print("  [校验] 分段检查全部通过 ✓")

    # ---- build id ----
    build_id = b[off + 0x30:off + 0x50].rstrip(b"\x00").hex()
    print(f"  [build id] {build_id}")

    # ---- heap 约束 ----
    if size > HEAP_DEFAULT:
        print(f"  ★ 文件 {size:,} 字节 > 默认 heap {HEAP_DEFAULT:,}"
              f"（HOS 21+），可能读不完整")
        ok = False
    else:
        print(f"  [heap] {size:,} 字节 < 默认 heap {HEAP_DEFAULT:,} ✓")

    # ---- 尾部 ULTR 签名 ----
    if b[-4:] == b"ULTR":
        print("  [ULTR] 末尾含 libultrahand 签名 ✓")
    else:
        print(f"  [ULTR] 末尾为 {b[-4:]!r}（非 libultrahand 构建，Ultrahand 会当作普通 overlay）")

    print()
    return ok


def main():
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        return 1

    allok = True
    for t in targets:
        p = Path(t)
        if not p.is_file():
            print(f"找不到 {p}\n")
            allok = False
            continue
        allok &= check(p)

    print("=" * 56)
    print("结果:", "全部通过" if allok else "存在问题")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
