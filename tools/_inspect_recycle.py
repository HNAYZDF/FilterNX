#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_inspect_recycle.py — 列出回收站里的项目、类型、原始位置

用途: 确认哪些是文件夹（恢复时需要不同处理），以及原始路径。
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

shell32 = ctypes.windll.shell32
shell32.SHGetFolderLocation.restype = ctypes.c_void_p


class SHITEMID(ctypes.Structure):
    _fields_ = [("cb", wt.USHORT), ("abID", wt.BYTE * 1)]


class ITEMIDLIST(ctypes.Structure):
    _fields_ = [("mkid", SHITEMID)]


SHGFP_TYPE_CURRENT = 0
CSIDL_BITBUCKET = 0x000A

# 用 SHGetFolderPathW 取回收站，再用 IShellFolder 太重，
# 改用简单可靠的方式: 直接读 C:\$Recycle.Bin\<SID> 目录结构。
recycle_root = r"C:\$Recycle.Bin"
print(f"=== 回收站原始目录 {recycle_root} ===\n")

if not os.path.isdir(recycle_root):
    print("  读不到（可能需要管理员权限）")
    sys.exit(0)

for sid in os.listdir(recycle_root):
    sid_dir = os.path.join(recycle_root, sid)
    if not os.path.isdir(sid_dir):
        continue
    entries = [e for e in os.listdir(sid_dir) if not e.startswith("desktop.ini")]
    if not entries:
        continue
    print(f"  [SID] {sid}   ({len(entries)} 项)")
    for e in sorted(entries):
        p = os.path.join(sid_dir, e)
        kind = "目录" if os.path.isdir(p) else "文件"
        size = 0
        if os.path.isfile(p):
            size = os.path.getsize(p)
        else:
            for root, _, files in os.walk(p):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        print(f"      {kind}  {e:<46} {size/1024:>10,.0f} KB")
    print()
