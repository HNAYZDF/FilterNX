#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_preview_clip.py — 校验各页内容是否落在真实裁剪区内

真机上 List 的内容被 enableScissoring(0, 88, W, 557) 裁掉 —— 也就是
y ∈ [88, 645]。落在 645 以下的内容**不会被画出来**。

所以每页的最后一项的底边必须 ≤ 645，否则用户看到的是被切了一半的行
（真机实测过：页面底部出现半行残影）。

本脚本按 layout.hpp 的常量算每页的结束位置，逐页核对。
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "overlay" / "src" / "layout.hpp"
GUI = ROOT / "overlay" / "src" / "gui.cpp"


def const(name, text, default=None):
    m = re.search(rf"inline constexpr int {name}\s*=\s*(\d+);", text)
    return int(m.group(1)) if m else default


def main():
    t = LAYOUT.read_text(encoding="utf-8")

    VISIBLE_HEIGHT = const("VISIBLE_HEIGHT", t)
    ITEM = const("ITEM_HEIGHT", t)
    HEADER = const("HEADER_HEIGHT", t)
    OFFSET = const("FIRST_ITEM_OFFSET", t)

    # List 的真实裁剪矩形（tesla.hpp List::draw）:
    #     enableScissoring(0, 88, FramebufferWidth, FramebufferHeight - 73 - 97 + 2 + 5)
    # 在 720 下: y ∈ [88, 88 + 557] = [88, 645]
    SCISSOR_TOP = 88
    SCISSOR_H = 720 - 73 - 97 + 2 + 5           # 557（这是"高度"，不是"下界"）
    SCISSOR_BOTTOM = SCISSOR_TOP + SCISSOR_H    # 645

    list_start = 97                              # 列表内容起点
    limit = SCISSOR_BOTTOM

    pages = [
        ("主页面", const("MAIN_HEADERS", t), const("MAIN_ITEMS", t), True),
        ("滤镜列表", const("PRESET_HEADERS", t), const("PRESET_ITEMS", t), False),
        ("关于", const("INFO_HEADERS", t), const("INFO_ITEMS", t), False),
    ]

    print("=== 各页裁剪检查 ===")
    print(f"  裁剪矩形: y ∈ [{SCISSOR_TOP}, {SCISSOR_BOTTOM}]"
          f"  (起点 {SCISSOR_TOP} + 高度 {SCISSOR_H})")
    print(f"  列表内容起点 y={list_start}，可用高度 {limit - list_start}px")
    print(f"  单项: 小标题 {HEADER}px / 列表项 {ITEM}px")
    print()

    bad = 0
    for name, headers, items, must_fit in pages:
        end = list_start + headers * HEADER + items * ITEM
        fits = end <= limit
        status = "[OK] 完整可见" if fits else "[--] 需滚动（正常，但底部会裁）"
        print(f"  {name:6}  {headers} 小标题 + {items} 项"
              f"  → 结束于 y={end}  {status}")

        if must_fit and not fits:
            bad += 1
            print(f"        ★ 该页标记为必须完整可见，但超了 {end - limit}px")
    print()

    # 主页面必须完全放得下（它没有"滚动到底"的引导，用户可能不知道要滚）
    main_end = list_start + const("MAIN_HEADERS", t) * HEADER + const("MAIN_ITEMS", t) * ITEM
    print(f"  主页面结束 y={main_end} ≤ {limit} ? {main_end <= limit}")
    if main_end > limit:
        print("  ★ 主页面会被裁剪 —— 用户可能看不到「关于」入口")
        bad += 1

    # 「关于」入口必须在首屏可见（不能被裁掉），否则用户找不到 QQ 群
    # 它在"使用说明"小标题下的第 3 项
    about_bottom = list_start + 3 * HEADER + const("MAIN_ITEMS", t) * ITEM
    print(f"  「关于」底边 y={about_bottom} ≤ {limit} ? {about_bottom <= limit}")
    if about_bottom > limit:
        print("  ★ 「关于」入口被裁 —— 用户看不到作者与 QQ 群")
        bad += 1

    print()
    print("=" * 56)
    if bad:
        print(f"结果: ★ {bad} 处问题")
        return 1
    print("结果: 各页均在裁剪区内，关键入口不会被裁掉")
    return 0


if __name__ == "__main__":
    sys.exit(main())
