#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_ps1_bom.py — 确认所有 .ps1 都是 UTF-8 with BOM

═══════════════════════════════════════════════════════════════════════════
为什么必须检查这个
═══════════════════════════════════════════════════════════════════════════
Windows PowerShell 5.1 读取**无 BOM** 的 .ps1 时按系统 ANSI 代码页解码。
项目里的脚本含大量中文注释与字符串，一旦没有 BOM:

    · 中文变成乱码
    · 乱码里的引号/括号会破坏词法分析
    · 结果是脚本**被当作代码逐行执行**，报出莫名其妙的语法错误
      （例如 `-ForegroundColor Cyan` 被当成命令）

这个坑踩过多次，而且每次表现都不一样。所以固化成检查项。

⚠ 注意: 用 edit 工具修改 .ps1 会**去掉 BOM**，改完必须补回来。
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"

checks = 0
fails = 0


def ck(cond, label, detail=""):
    global checks, fails
    checks += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        if detail:
            print(f"        {detail}")
        fails += 1


def main():
    print("=== PowerShell 脚本 BOM 检查 ===\n")

    scripts = sorted(ROOT.rglob("*.ps1"))
    scripts = [p for p in scripts if "build" not in p.parts]
    ck(bool(scripts), f"找到 {len(scripts)} 个 .ps1")

    bad = []
    for p in scripts:
        head = p.read_bytes()[:3]
        if head != BOM:
            bad.append(p.relative_to(ROOT).as_posix())
        else:
            print(f"  PASS  {p.relative_to(ROOT).as_posix()}")

    if bad:
        print()
        ck(False, f"全部 .ps1 都带 UTF-8 BOM（{len(bad)} 个缺失）",
           "缺少 BOM: " + ", ".join(bad) +
           "  —— PowerShell 5.1 会按 ANSI 解码，中文脚本会崩")
    else:
        ck(True, f"全部 {len(scripts)} 个 .ps1 都带 UTF-8 BOM")

    print()
    print("=" * 58)
    if fails:
        print(f"结果: ★ {fails} 项不通过")
        print("      修复: 用 [System.IO.File]::WriteAllText 配 UTF8Encoding($true) 重写")
        return 1
    print("结果: 全部脚本 BOM 正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
