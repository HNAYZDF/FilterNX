#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 version.hpp 的 FNX_VERSION 改为指定值（避免 PowerShell 引号地狱）。"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HPP = ROOT / "overlay" / "src" / "version.hpp"

if len(sys.argv) < 2:
    print("用法: set_version.py <版本号>")
    sys.exit(1)

new_ver = sys.argv[1]
text = HPP.read_text(encoding="utf-8")

old = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"', text, re.M)
if not old:
    print("[FAIL] 找不到 FNX_VERSION")
    sys.exit(1)

text = re.sub(r'^(#define\s+FNX_VERSION\s+")[^"]+(")',
              rf'\g<1>{new_ver}\g<2>', text, count=1, flags=re.M)
HPP.write_text(text, encoding="utf-8")

check = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"',
                  HPP.read_text(encoding="utf-8"), re.M)
print(f"  版本号: {old.group(1)} -> {check.group(1)}")
