#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_preset_table.py — 静态解析 presets.hpp，逐个检查条目字段

比编译更快定位"某个条目少写了字段"这类问题。
test_presets 崩溃在 std::string(nullptr) 就是这类问题。
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src" / "presets.hpp"

ENTRY = re.compile(
    r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*PresetGroup::(\w+)',
)


def main():
    text = SRC.read_text(encoding="utf-8")

    i = text.find("std::array<Preset,")
    j = text.find("}};", i)
    if i < 0 or j < 0:
        print("[FAIL] 找不到预设表定义")
        return 1

    body = text[i:j]
    entries = ENTRY.findall(body)

    # 用 "{" 计数粗算实际条目数，与正则命中数对比
    brace_entries = len(re.findall(r'^\s*\{ "', body, re.M))

    print(f"=== presets.hpp 条目检查 ===")
    print(f"  正则命中 : {len(entries)}")
    print(f"  左花括号 : {brace_entries}")
    if len(entries) != brace_entries:
        print(f"  ★ 有 {brace_entries - len(entries)} 个条目的字段格式不符合预期")
    print()

    bad = 0
    seen_ids, seen_names = set(), set()
    for k, (pid, name, desc, grp) in enumerate(entries):
        flags = []
        if not pid:   flags.append("id 为空")
        if not name:  flags.append("name 为空")
        if not desc:  flags.append("desc 为空")
        if len(name) > 4: flags.append(f"name {len(name)} 字 >4")
        if len(desc) > 5: flags.append(f"desc {len(desc)} 字 >5")
        if pid in seen_ids:   flags.append("id 重复")
        if name in seen_names: flags.append("name 重复")
        seen_ids.add(pid)
        seen_names.add(name)

        if flags:
            bad += 1
            print(f"  ★ [{k}] {pid!r} / {name!r} / {desc!r}  ->  {', '.join(flags)}")

    print(f"  共检查 {len(entries)} 条，问题 {bad} 处")

    # 列出全部分类名
    groups = sorted({g for _, _, _, g in entries})
    print(f"\n  出现的分类: {', '.join(groups)}")

    print()
    if bad:
        print("结果: ★ 存在格式问题")
        return 1
    print("结果: 全部条目字段格式正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
