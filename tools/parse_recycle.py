#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_recycle.py — 直接解析 $Recycle.Bin 的 $I 元数据文件

═══════════════════════════════════════════════════════════════════════════
为什么要直接解析
═══════════════════════════════════════════════════════════════════════════
Shell 的回收站视图（Namespace(10)）有时显示不全 —— 实测出现
「C:\\$Recycle.Bin 里有 50 个文件，但界面显示 0 项」的情况。

$I 文件格式（Vista 之后，版本 2）:
    偏移  大小  含义
    0x00  8     头（版本号，通常 02 00 ...）
    0x08  8     被删文件大小 (u64)
    0x10  8     删除时间 (FILETIME, u64)
    0x18  4     路径长度（字符数，含结尾 NUL）  ← 版本 2 才有
    0x1C  ...   原始完整路径 (UTF-16LE)

$R 文件才是内容本体，与 $I 同名（前缀 $I -> $R）。
═══════════════════════════════════════════════════════════════════════════
"""

import datetime
import os
import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DRIVES = ["C:", "D:", "E:", "F:"]


def filetime_to_dt(ft: int):
    if ft == 0:
        return None
    try:
        return datetime.datetime(1601, 1, 1) + datetime.timedelta(
            microseconds=ft // 10)
    except Exception:
        return None


def parse_i(p: Path):
    """解析一个 $I 文件，返回 (原始路径, 删除时间, 大小)"""
    try:
        b = p.read_bytes()
    except OSError:
        return None
    if len(b) < 0x18:
        return None

    size = struct.unpack_from("<Q", b, 0x08)[0]
    ft = struct.unpack_from("<Q", b, 0x10)[0]
    dt = filetime_to_dt(ft)

    path = None
    if len(b) >= 0x1C:
        nchars = struct.unpack_from("<I", b, 0x18)[0]
        # 版本 1 的 nchars 可能是 0 或异常大
        if 0 < nchars <= 1024:
            raw = b[0x1C:0x1C + nchars * 2]
            try:
                path = raw.decode("utf-16-le").rstrip("\x00")
            except Exception:
                path = None
    if path is None:
        # 退回: 整个尾部按 UTF-16 解，取到第一个 NUL
        try:
            tail = b[0x1C:]
            s = tail.decode("utf-16-le", "replace")
            path = s.split("\x00")[0]
        except Exception:
            path = None
    return path, dt, size


def main():
    entries = []
    for d in DRIVES:
        root = Path(f"{d}/$Recycle.Bin")
        if not root.is_dir():
            continue
        for sid_dir in root.iterdir():
            if not sid_dir.is_dir():
                continue
            try:
                names = os.listdir(sid_dir)
            except OSError:
                continue
            for n in names:
                if not n.startswith("$I"):
                    continue
                p = sid_dir / n
                r = parse_i(p)
                if r is None:
                    continue
                path, dt, size = r
                # 对应的 $R（内容）
                rname = "$R" + n[2:]
                rpath = sid_dir / rname
                kind = "目录" if rpath.is_dir() else (
                    "文件" if rpath.is_file() else "缺失")
                entries.append({
                    "drive": d, "i": n, "r": rname, "path": path,
                    "dt": dt, "size": size, "kind": kind,
                    "rpath": str(rpath),
                })

    entries.sort(key=lambda e: e["dt"] or datetime.datetime.min,
                 reverse=True)

    print(f"=== 回收站元数据解析: 共 {len(entries)} 项 ===\n")
    for e in entries:
        t = e["dt"].strftime("%m-%d %H:%M") if e["dt"] else "?"
        sz = e["size"] / 1024
        unit = f"{sz:,.0f} KB"
        if sz > 1024:
            unit = f"{sz/1024:,.1f} MB"
        if sz > 1024 * 1024:
            unit = f"{sz/1024/1024:,.2f} GB"
        print(f"  {t}  [{e['kind']}] {unit:>10}  {e['path']}")
        print(f"            {e['rpath']}")

    # 统计桌面来源的
    desk = [e for e in entries
            if e["path"] and "Desktop" in e["path"].replace("/", "\\")]
    print()
    print(f"  其中原位置在桌面的: {len(desk)} 项")
    for e in desk:
        t = e["dt"].strftime("%m-%d %H:%M") if e["dt"] else "?"
        print(f"    {t}  [{e['kind']}]  {e['path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
