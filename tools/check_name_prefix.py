#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_name_prefix.py — 检查预设名字之间是否存在"前缀包含"关系

为什么这是个真问题:
    界面上的名字是用户唯一的识别依据。如果 A 是 B 的前缀
    （例如「黑白」与「黑白硬调」），用户在列表里快速扫过时极易看错，
    按下去得到的效果却不同。

本脚本独立于 C++ 测试，用于快速定位是哪一对（C++ 测试只报通过/失败）。
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SRC = Path(__file__).resolve().parent.parent / "overlay" / "src" / "presets.hpp"
text = SRC.read_text(encoding="utf-8")

i = text.find("std::array<Preset,")
j = text.find("}};", i)
body = text[i:j]

ENTRY = re.compile(r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*PresetGroup::(\w+)')
entries = ENTRY.findall(body)

print(f"=== 预设名字前缀检查（共 {len(entries)} 个）===\n")

bad = 0
for a_id, a_name, _, _ in entries:
    for b_id, b_name, _, _ in entries:
        if a_id == b_id:
            continue
        if len(a_name) < len(b_name) and b_name.startswith(a_name):
            bad += 1
            print(f"  ★ 「{a_name}」({a_id}) 是 「{b_name}」({b_id}) 的前缀")

print()
if bad:
    print(f"结果: ★ 发现 {bad} 处前缀包含关系，界面上容易看错")
else:
    print("结果: 没有名字是另一个的前缀")

# 顺便列出所有名字，便于人工扫一眼
print("\n全部名字:")
for k, (pid, name, desc, grp) in enumerate(entries, 1):
    print(f"  {k:2}. {name:<6} {desc:<7} [{grp}]")

sys.exit(1 if bad else 0)
