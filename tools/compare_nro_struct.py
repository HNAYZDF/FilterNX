#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_nro_struct.py — 把我的 overlay 与已知可用 overlay 做结构级并排比对

动机: nx-ovlloader 加载 overlay 时会校验 NRO 头，不通过就 fatalThrow
（表现为整个 Tesla 崩掉）。因此必须确认我的产物在**结构上**与已知能正常
加载的 overlay 完全同构，而不只是"我的字段自洽"。

比对维度:
  · NroStart（0x00）     — 入口跳转指令与 mod_offset
  · NroHeader（0x10）    — magic / size / unk 字段
  · 段布局               — 段数量、对齐、偏移递增关系
  · 段后附加数据          — NACP / icon 资源段（mod_offset 指向处）
  · 文件末尾             — ULTR 签名
"""

import struct
import sys
from pathlib import Path

NROSTART_SIZE = 0x10
HDR = NROSTART_SIZE


def parse(p: Path):
    b = p.read_bytes()
    d = {}
    d["path"] = p
    d["size"] = len(b)

    (d["entry"], d["mod_offset"]) = struct.unpack_from("<II", b, 0)
    (d["magic"], d["unk1"], d["hsize"], d["unk2"]) = struct.unpack_from("<IIII", b, HDR)
    d["magic_raw"] = b[HDR:HDR + 4]

    segs = []
    for i in range(3):
        fo, sz = struct.unpack_from("<II", b, HDR + 0x10 + i * 8)
        segs.append((fo, sz))
    d["segs"] = segs
    (d["bss"], d["unk3"]) = struct.unpack_from("<II", b, HDR + 0x28)
    d["build_id"] = b[HDR + 0x30:HDR + 0x50].rstrip(b"\x00").hex()
    d["ultr"] = (b[-4:] == b"ULTR")

    # 段是否首尾相接且从 0 开始
    d["seg_contiguous"] = (segs[0][0] == 0 and
                           segs[1][0] == segs[0][0] + segs[0][1] and
                           segs[2][0] == segs[1][0] + segs[1][1])
    # 三段总和 == header->size ?
    d["seg_sum"] = segs[0][1] + segs[1][1] + segs[2][1]
    d["sum_eq_hsize"] = (d["seg_sum"] == d["hsize"])
    # 资源段位置
    d["assets_off"] = d["mod_offset"]
    d["has_assets"] = 0 < d["mod_offset"] < len(b)
    if d["has_assets"]:
        # NroAssetHeader: magic "ASET" + version + 三个 (u64 off, u64 size)
        ao = d["mod_offset"]
        d["asset_magic"] = b[ao:ao + 4]
        try:
            (ver,) = struct.unpack_from("<I", b, ao + 4)
            d["asset_version"] = ver
            d["asset_sections"] = []
            for i in range(3):
                off, sz = struct.unpack_from("<QQ", b, ao + 8 + i * 16)
                d["asset_sections"].append((off, sz))
        except Exception:
            d["asset_magic"] = b"?"
    return d


def show(d):
    p = d["path"]
    print(f"--- {p.name}")
    print(f"    文件大小      : {d['size']:,}")
    print(f"    NroStart      : entry=0x{d['entry']:08X}  mod_offset=0x{d['mod_offset']:X}")
    print(f"    NroHeader     : magic={d['magic_raw']} (0x{d['magic']:08X})  "
          f"hsize={d['hsize']:,} (0x{d['hsize']:X})")
    print(f"                    unk1=0x{d['unk1']:X} unk2=0x{d['unk2']:X} unk3=0x{d['unk3']:X}")
    for i, (fo, sz) in enumerate(d["segs"]):
        nm = [".text", ".rodata", ".data"][i]
        print(f"    段 {nm:8}   : file_off=0x{fo:X} size=0x{sz:X} ({sz:,})")
    print(f"    bss_size      : 0x{d['bss']:X} ({d['bss']:,})")
    print(f"    段首尾相接    : {d['seg_contiguous']}")
    print(f"    段总和==hsize : {d['sum_eq_hsize']}  ({d['seg_sum']:,} vs {d['hsize']:,})")
    print(f"    资源段        : {'有' if d['has_assets'] else '无'}"
          + (f"  magic={d.get('asset_magic')} ver={d.get('asset_version')}"
             if d["has_assets"] else ""))
    if d.get("asset_sections"):
        for i, (off, sz) in enumerate(d["asset_sections"]):
            nm = ["icon", "nacp", "romfs"][i]
            print(f"      {nm:6}: off=0x{off:X} size={sz:,}")
    print(f"    ULTR 签名     : {d['ultr']}")
    print(f"    build id      : {d['build_id']}")
    print()


def main():
    targets = [Path(a) for a in sys.argv[1:]]
    if not targets:
        print(__doc__)
        return 1

    parsed = []
    for t in targets:
        if not t.is_file():
            print(f"找不到 {t}")
            continue
        parsed.append(parse(t))

    for d in parsed:
        show(d)

    if len(parsed) < 2:
        return 0

    print("=" * 62)
    print("结构一致性检查（以第一个为基准）")
    print("=" * 62)
    base = parsed[0]
    ok = True
    for d in parsed[1:]:
        issues = []
        if d["magic_raw"] != base["magic_raw"]:
            issues.append(f"magic 不同: {d['magic_raw']} vs {base['magic_raw']}")
        if d["seg_contiguous"] != base["seg_contiguous"]:
            issues.append("段连续性不同")
        if d["sum_eq_hsize"] != base["sum_eq_hsize"]:
            issues.append("段总和==hsize 关系不同")
        if d["has_assets"] != base["has_assets"]:
            issues.append("资源段存在性不同")
        if d.get("asset_magic") != base.get("asset_magic"):
            issues.append(f"资源段 magic 不同: {d.get('asset_magic')} vs {base.get('asset_magic')}")
        if d["entry"] != base["entry"]:
            issues.append(f"NroStart entry 不同: 0x{d['entry']:08X} vs 0x{base['entry']:08X}")

        if issues:
            ok = False
            print(f"  ★ {d['path'].name} 与基准有差异:")
            for x in issues:
                print(f"      - {x}")
        else:
            print(f"  ✓ {d['path'].name} 与基准结构一致")

    print()
    print("结果:", "结构一致" if ok else "存在结构差异")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
