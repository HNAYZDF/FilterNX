#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_region.py — 按偏移区间 dump 二进制中的可读字符串

用于分析 4IFIR.ovl 中 DC Dimming 相关的界面文案与寄存器名，
从而判断其实现方式。
"""

import re
import sys
from pathlib import Path

UTF8_RE = re.compile(
    rb"(?:[\x20-\x7e]|[\xc2-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf4][\x80-\xbf]{3}){4,}"
)


def main():
    path = Path(sys.argv[1])
    lo = int(sys.argv[2], 0)
    hi = int(sys.argv[3], 0)

    data = path.read_bytes()[lo:hi]
    print(f"# {path.name}  区间 0x{lo:X}..0x{hi:X}  ({len(data):,} 字节)\n")

    for m in UTF8_RE.finditer(data):
        try:
            s = m.group().decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if len(s) < 3:
            continue
        print(f"{lo + m.start():08X}  {s}")


if __name__ == "__main__":
    main()
