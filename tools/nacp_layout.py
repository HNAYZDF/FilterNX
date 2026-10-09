#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nacp_layout.py — NACP 结构布局的唯一定义

═══════════════════════════════════════════════════════════════════════════
为什么单独抽出来
═══════════════════════════════════════════════════════════════════════════
NACP 的偏移曾经在多个脚本里各写一份，结果 set_nacp.py 与 read_nacp.py
错得**一致**（都把 display_version 当成 0x3000），于是"写入后回读校验通过"
成了假通过 —— 两边犯同一个错，互相验证不出来。

现在所有脚本都 import 这一份定义，只要这里是对的，所有脚本就对。

常量来源: libnx switch/nacp.h + tools/nacp_offsets.c（用编译器实测）
═══════════════════════════════════════════════════════════════════════════
"""

import struct

# ── NacpLanguageEntry: { char name[0x200]; char author[0x100]; } ──
LANG_STRIDE = 0x300      # 每个语言项的大小（不是 0x200 —— 那是 name 的大小）
NAME_OFF    = 0x000      # 语言项内 name 偏移
NAME_SIZE   = 0x200
AUTHOR_OFF  = 0x200      # 语言项内 author（发行商）偏移
AUTHOR_SIZE = 0x100

# ── lang_data 之后的标量字段 ──
LANG_DATA_SIZE = LANG_STRIDE * 16        # 0x3000
ISBN_OFF       = 0x3000                  # u8 isbn[0x25]
ISBN_SIZE      = 0x25
# 0x3025 startup_user_account, 0x3026 user_account_switch_lock,
# 0x3027 add_on_content_registration_type, 0x3028 attribute_flag(u32),
# 0x302C supported_language_flag(u32), 0x3030 parental_control_flag(u32),
# 0x3034 screenshot, 0x3035 video_capture, 0x3036 data_loss_confirmation,
# 0x3037 play_log_policy, 0x3038 presence_group_id(u64),
# 0x3040 rating_age[0x20]
DISPLAY_VERSION_OFF  = 0x3060            # char display_version[0x10]  ← 版本在这
DISPLAY_VERSION_SIZE = 0x10

LANG_COUNT = 16

# 语言索引（libnx 的 NacpLanguage 枚举顺序）
LANGS = [
    "AmericanEnglish", "BritishEnglish", "Japanese", "French",
    "German", "LatinAmericanSpanish", "Spanish", "Italian",
    "Dutch", "CanadianFrench", "Portuguese", "Russian",
    "Korean", "TraditionalChinese", "SimplifiedChinese", "Reserved",
]

# Ultrahand / Tesla 菜单读取的槽位（源码依据: Ultrahand utils.hpp:1043）
MENU_NAME_LANG_INDEX = 0


def find_nacp(b: bytes):
    """在 NRO 字节流里定位 NACP。

    NRO 资源段以 "ASET" 开头:
        magic[4] version[4] 然后三个 (u64 offset, u64 size) = icon, nacp, romfs
    offset 相对 ASET 起点。

    返回 (nacp绝对偏移 或 None, aset偏移 或 None, 资源段列表 或 None)
    """
    idx = b.find(b"ASET")
    if idx < 0:
        return None, None, None

    sections = []
    for i in range(3):
        o, s = struct.unpack_from("<QQ", b, idx + 8 + i * 16)
        sections.append((o, s))

    nacp_off, nacp_size = sections[1]
    if nacp_size == 0:
        return None, idx, sections

    return idx + nacp_off, idx, sections


def read_cstr(raw: bytes) -> str:
    """按 NUL 截断并解码为 UTF-8"""
    nul = raw.find(b"\x00")
    if nul >= 0:
        raw = raw[:nul]
    try:
        return raw.decode("utf-8")
    except Exception:
        return f"<非 UTF-8: {raw[:16].hex()}>"


def get_name(b: bytes, nacp_off: int, lang: int = MENU_NAME_LANG_INDEX) -> str:
    base = nacp_off + lang * LANG_STRIDE + NAME_OFF
    return read_cstr(b[base:base + NAME_SIZE])


def get_author(b: bytes, nacp_off: int, lang: int = MENU_NAME_LANG_INDEX) -> str:
    base = nacp_off + lang * LANG_STRIDE + AUTHOR_OFF
    return read_cstr(b[base:base + AUTHOR_SIZE])


def get_version(b: bytes, nacp_off: int) -> str:
    base = nacp_off + DISPLAY_VERSION_OFF
    return read_cstr(b[base:base + DISPLAY_VERSION_SIZE])


def get_isbn(b: bytes, nacp_off: int) -> str:
    base = nacp_off + ISBN_OFF
    return read_cstr(b[base:base + ISBN_SIZE])
