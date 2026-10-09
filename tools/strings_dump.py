#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
strings_dump.py — 从二进制里提取可读字符串

用于分析 4IFIR 分发中与"DC 调光"相关的模块到底是什么实现。
支持 ASCII 与 UTF-8（中文）两种串的提取。
"""

import re
import sys
from pathlib import Path

MIN_LEN = 4

# ASCII 可打印串
ASCII_RE = re.compile(rb"[\x20-\x7e]{%d,}" % MIN_LEN)
# UTF-8 串（含中文）：把连续的多字节 UTF-8 与 ASCII 一起抓出来
UTF8_RE = re.compile(
    rb"(?:[\x20-\x7e]|[\xc2-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf4][\x80-\xbf]{3}){%d,}" % MIN_LEN
)


def dump(path: Path, mode: str, keywords: list[str] | None, limit: int):
    data = path.read_bytes()
    regex = UTF8_RE if mode == "utf8" else ASCII_RE

    seen = set()
    count = 0
    for m in regex.finditer(data):
        raw = m.group()
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        s = s.strip()
        if len(s) < MIN_LEN or s in seen:
            continue

        if keywords:
            low = s.lower()
            if not any(k.lower() in low for k in keywords):
                continue

        seen.add(s)
        print(f"{m.start():08X}  {s}")
        count += 1
        if limit and count >= limit:
            print(f"... (达到上限 {limit})")
            return


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    path = Path(sys.argv[1])
    mode = "utf8"
    keywords = None
    limit = 0

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--ascii":
            mode = "ascii"
        elif a == "--utf8":
            mode = "utf8"
        elif a == "--grep":
            i += 1
            keywords = args[i].split(",")
        elif a == "--limit":
            i += 1
            limit = int(args[i])
        i += 1

    if not path.is_file():
        print(f"找不到文件: {path}")
        return 1

    print(f"# {path.name}  ({path.stat().st_size:,} 字节, 模式={mode}"
          f"{', 关键词=' + ','.join(keywords) if keywords else ''})\n")
    dump(path, mode, keywords, limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
