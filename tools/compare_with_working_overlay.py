#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_with_working_overlay.py — 把本插件与卡上正常工作的 overlay 逐项对比

═══════════════════════════════════════════════════════════════════════════
思路（用户提的）
═══════════════════════════════════════════════════════════════════════════
既然卡上有一堆**能正常工作**的 overlay，而只有本插件在
「Fizeau 未运行」时出事，那就把它们逐项对比 —— 找差异比凭空猜有效。

重点看 sys-tune-overlay.ovl: 它 671,804 字节，与本插件 682,185 最接近，
两者都用 libultrahand，结构应当高度相似。

对比项:
  · NRO 头各字段（段偏移/大小/对齐）
  · 段表三项（icon / nacp / romfs）的布局
  · 运行期映像大小（text + rodata + bss）—— 直接关系 overlay 堆
  · NACP 元数据（名字/版本/作者）
  · 尾部签名（ULTR）
"""

import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MINE = ROOT / "overlay" / "FilterNX.ovl"

# 参照: 卡上正常工作的 overlay（来自 SD 卡副本）
CANDIDATES = [
    Path("F:/ai/final-sd/switch/.overlays/sys-tune-overlay.ovl"),
    Path("F:/ai/final-sd/switch/.overlays/ovl-sysmodules.ovl"),
    Path("F:/ai/final-sd/switch/.overlays/ReverseNX-RT.ovl"),
    Path("F:/ai/final-sd/switch/.overlays/Nx-FanControl.ovl"),
    Path("F:/ai/final-sd/switch/.overlays/ovlmenu.ovl"),
]

sys.path.insert(0, str(ROOT / "tools"))
from nacp_layout import find_nacp, get_name, get_version, get_author  # noqa: E402


def nro_info(b: bytes):
    """解析 NRO 头"""
    if len(b) < 0x40 or b[0x10:0x14] != b"NRO0":
        return None
    d = {}
    d["size"] = len(b)
    d["header_ver"] = struct.unpack_from("<I", b, 0x14)[0]
    d["nro_size"] = struct.unpack_from("<I", b, 0x18)[0]
    # 0x1C: 8 字节 flags/保留；0x24 起为三段 {u32 off, u32 size}
    d["text"] = struct.unpack_from("<II", b, 0x24)
    d["ro"] = struct.unpack_from("<II", b, 0x2C)
    d["data"] = struct.unpack_from("<II", b, 0x34)
    d["bss_size"] = struct.unpack_from("<I", b, 0x3C)[0]
    d["tail"] = b[-4:] if len(b) >= 4 else b""
    return d


def main():
    print("=== 与卡上正常工作的 overlay 逐项对比 ===\n")

    if not MINE.is_file():
        print(f"找不到 {MINE}")
        return 1

    refs = [p for p in CANDIDATES if p.is_file()]
    if not refs:
        print("找不到任何参照 overlay（F:/ai/final-sd 副本）")
        return 1

    items = [("本插件", MINE)] + [(p.stem, p) for p in refs]

    print(f"{'名称':<24} {'文件':>10} {'text':>9} {'rodata':>8} {'data':>8} "
          f"{'bss':>8} {'映像':>9}")
    print("-" * 82)

    infos = {}
    for label, p in items:
        b = p.read_bytes()
        n = nro_info(b)
        if not n:
            print(f"{label:<24} ★ 不是合法 NRO")
            continue
        infos[label] = (p, b, n)
        img = n["text"][1] + n["ro"][1] + n["data"][1] + n["bss_size"]
        print(f"{label:<24} {n['size']:>10,} {n['text'][1]:>9,} {n['ro'][1]:>8,} "
              f"{n['data'][1]:>8,} {n['bss_size']:>8,} {img:>9,}")

    print()

    # ── 映像大小对比（直接关系 overlay 堆）──
    print("[运行期映像大小 —— 直接决定需要的 overlay 堆]")
    mine_img = None
    for label, (p, b, n) in infos.items():
        img = n["text"][1] + n["ro"][1] + n["data"][1] + n["bss_size"]
        if label == "本插件":
            mine_img = img
        flag = ""
        if img > 4 * 1024 * 1024:
            flag = "  ★ 超过 4MB"
        print(f"    {label:<24} {img:>10,} 字节  ({img/1024/1024:.2f} MB){flag}")

    if mine_img is not None:
        others = [n["text"][1] + n["ro"][1] + n["data"][1] + n["bss_size"]
                  for lab, (p, b, n) in infos.items() if lab != "本插件"]
        if others:
            mx = max(others)
            print()
            print(f"    参照中最大: {mx:,} 字节")
            if mine_img > mx:
                print(f"    → 本插件映像比所有参照都大 "
                      f"（多 {mine_img - mx:,} 字节，{(mine_img-mx)/mx*100:.0f}%）")
            else:
                print(f"    → 本插件映像未超过参照最大值（说明堆大小不是问题）")

    # ── NACP 对比 ──
    print()
    print("[NACP 元数据]")
    for label, (p, b, n) in infos.items():
        off, _, _ = find_nacp(b)
        if off is None:
            print(f"    {label:<24} （无 NACP）")
            continue
        nm = get_name(b, off)
        vr = get_version(b, off)
        au = get_author(b, off)
        print(f"    {label:<24} 名字={nm!r:<18} 版本={vr!r:<10} 作者={au!r}")

    # ── 尾部签名 ──
    print()
    print("[尾部 4 字节（ULTR 签名）]")
    for label, (p, b, n) in infos.items():
        print(f"    {label:<24} {n['tail']!r}")

    print()
    print("=" * 64)
    print("结论:")
    print("  · 若本插件映像明显大于所有参照 → 堆大小是嫌疑")
    print("  · 若大小相当 → 堆不是问题，须从别处找")
    return 0


if __name__ == "__main__":
    sys.exit(main())
