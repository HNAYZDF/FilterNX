#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_restore_recycle.py — 查看（并可选择性恢复）回收站项目

用 Shell COM，避免直接读 C:\\$Recycle.Bin 的权限问题。

用法:
    python _restore_recycle.py list      # 只看
    python _restore_recycle.py restore   # 全部恢复
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

mode = sys.argv[1] if len(sys.argv) > 1 else "list"

try:
    import win32com.client  # noqa
    have_pywin32 = True
except ImportError:
    have_pywin32 = False

if not have_pywin32:
    print("  没有 pywin32，改用 PowerShell 方案")
    sys.exit(2)

shell = win32com.client.Dispatch("Shell.Application")
rb = shell.Namespace(10)          # 10 = Recycle Bin
items = rb.Items()
print(f"  回收站共 {items.Count} 项\n")

rows = []
for it in items:
    name = it.Name
    # IsFolder 判断
    is_folder = it.IsFolder
    size = it.Size
    rows.append((name, is_folder, size))

print("  ── 文件夹（恢复时需注意）──")
for n, f, s in rows:
    if f:
        print(f"    {n}")
print()
print("  ── 文件 ──")
for n, f, s in rows:
    if not f:
        print(f"    {n}   {s/1024:,.0f} KB")

if mode == "restore":
    print()
    print("  开始恢复…")
    ok = 0
    for it in items:
        try:
            # Verb "还原" / "Restore" 与位置无关
            for verb in it.Verbs():
                vn = verb.Name.replace("&", "")
                if vn in ("还原", "复原", "Restore"):
                    verb.DoIt()
                    ok += 1
                    print(f"    ✓ {it.Name}")
                    break
        except Exception as e:
            print(f"    ★ {it.Name}: {e}")
    print(f"  已恢复 {ok} 项")
