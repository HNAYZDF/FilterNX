#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nro_sections.py — 正确的 NRO 段表解析（唯一来源）

═══════════════════════════════════════════════════════════════════════════
NRO 头布局（偏移相对文件起点）
═══════════════════════════════════════════════════════════════════════════
    0x00  "NRO0" 之前是 homebrew 的 "HOMEBREW" 标记区
    0x10  magic  "NRO0"
    0x14  version (u32)
    0x18  size    (u32)
    0x1C  flags   (8 字节)
    0x20  text   { u32 file_offset, u32 size }   ← 注意是 0x20！
    0x28  rodata { u32 file_offset, u32 size }
    0x30  data   { u32 file_offset, u32 size }
    0x38  bss_size (u32)

⚠ 踩过的坑: 我一度按 0x24 / 0x2C / 0x34 解析（错位 4 字节），
  于是"段范围"全错，搜不到服务名字符串，得出**服务名没编进产物**的
  错误结论，并据此怀疑连接不可能成功 —— 白白折腾一轮。

  段表里的 offset 是**文件绝对偏移**（与 libnx 的 NroHeader 一致），
  不是相对 .text 的偏移。

  所以解析 NRO 段表**必须**用本文件这个函数，不要再手抄偏移。
═══════════════════════════════════════════════════════════════════════════
"""

import struct


def parse_nro_header(b: bytes):
    """解析 NRO 头，返回 dict；不是合法 NRO 时返回 None"""
    if len(b) < 0x40 or b[0x10:0x14] != b"NRO0":
        return None

    def seg(off):
        o, s = struct.unpack_from("<II", b, off)
        return {"offset": o, "size": s}

    return {
        "version": struct.unpack_from("<I", b, 0x14)[0],
        "size": struct.unpack_from("<I", b, 0x18)[0],
        "text": seg(0x20),
        "rodata": seg(0x28),
        "data": seg(0x30),
        "bss_size": struct.unpack_from("<I", b, 0x38)[0],
    }


def section_bytes(b: bytes, name: str):
    """取某个段的字节（越界时截断到文件末尾）"""
    h = parse_nro_header(b)
    if h is None or name not in h:
        return b""
    seg = h[name]
    a = seg["offset"]
    z = min(a + seg["size"], len(b))
    return b[a:z]


def find_bytes(b: bytes, needle: bytes):
    """在整个文件里找（不限段）"""
    i = b.find(needle)
    return i if i >= 0 else None


def describe(b: bytes):
    """返回可读的段信息字符串"""
    h = parse_nro_header(b)
    if h is None:
        return "不是合法 NRO"
    parts = []
    for n in ("text", "rodata", "data"):
        s = h[n]
        parts.append(f"{n} 0x{s['offset']:X}+{s['size']:,}")
    parts.append(f"bss {h['bss_size']:,}")
    return "  ".join(parts)
