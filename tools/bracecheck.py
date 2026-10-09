#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_braces.py — 按行统计 C++ 花括号深度，定位失衡处（跳过注释与字符串）"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def strip_code(line, state):
    out = []
    i = 0
    n = len(line)
    while i < n:
        if state["block"]:
            j = line.find("*/", i)
            if j < 0:
                return "".join(out)
            state["block"] = False
            i = j + 2
            continue
        c = line[i]
        nxt = line[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            break
        if c == "/" and nxt == "*":
            state["block"] = True
            i += 2
            continue
        if c == '"':
            i += 1
            while i < n:
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if c == "'":
            i += 1
            while i < n:
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else "filternx/overlay/src/presets.hpp")
    lines = path.read_text(encoding="utf-8").split("\n")

    state = {"block": False}
    depth = 0
    trace = []
    bad = False
    for ln, raw in enumerate(lines, 1):
        code = strip_code(raw, state)
        depth += code.count("{") - code.count("}")
        trace.append((ln, depth, raw))
        if depth < 0:
            print(f"  * 第 {ln} 行深度变负 —— 多了一个 }}")
            print(f"      {raw[:90]}")
            bad = True
            depth = 0

    print(f"=== {path.name} ===")
    print(f"  最终深度: {depth}  {'(平衡)' if depth == 0 else '(少 ' + str(depth) + ' 个) <-- 问题'}")

    if depth != 0 or bad:
        print()
        print("  最后 26 行深度轨迹:")
        for ln, d, raw in trace[-26:]:
            print(f"    {ln:4}: d={d:2}  {raw[:74]}")

    return 0 if depth == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
