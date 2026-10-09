#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svc_name_check.py — 正确验证服务名是否编入产物

═══════════════════════════════════════════════════════════════════════════
为什么不能简单搜字节流
═══════════════════════════════════════════════════════════════════════════
编译器把短字符串**内联成 AArch64 指令的立即数**，而不是放进 .rodata:

    6804: mov  x1, #0x6966         编码字节 66 69 = 'f','i'
    6808: movk x1, #0x657a, lsl 16 编码字节 7a 65 = 'z','e'
    6810: movk x1, #0x7561, lsl 32 编码字节 61 75 = 'a','u'
    6814: bl   smGetServiceWrapper

所以内存里的字节序列是:

    66 69 ?? ?? | 7a 65 ?? ?? | 61 75 ?? ??

—— 真实的 "fizeau" 被**每 4 字节跳过 2 字节**地拆开了。
`b"fizeau" in nro_bytes` 必然返回 False，**但功能完全正常**。

我一度据此断定「服务名没编进产物、连接不可能成功」，白白折腾一轮。
真正的判据是: **按指令边界还原立即数**（本脚本的做法）。

═══════════════════════════════════════════════════════════════════════════
做法
═══════════════════════════════════════════════════════════════════════════
在 .text 里找形如 `mov Xd, #imm16` / `movk Xd, #imm16, lsl #shift` 的指令，
按目标寄存器把片段拼起来，看是否能还原出指定的服务名。
"""

import struct


def _movz_movk_parts(instr: int):
    """判断是否 MOVZ/MOVK，返回 (reg, imm16, shift)；不是则返回 None

    AArch64 编码:
        MOVZ  Xd, #imm16, LSL #shift : 1_10_100101_hw_imm16_Rd  (64 位 sf=1)
        MOVK  Xd, #imm16, LSL #shift : 1_11_100101_hw_imm16_Rd
        其中 hw 两位决定 shift = hw*16
    """
    opc = (instr >> 29) & 0x3        # sf(1) + opc(1)
    fixed = (instr >> 23) & 0x3F     # 100101
    if sf_ok := (opc in (0x2, 0x3)):  # 64 位: sf=1 → opc 位为 10/11
        pass
    else:
        return None
    if fixed != 0x25:                # 0b100101
        return None
    hw = (instr >> 21) & 0x3
    imm16 = (instr >> 5) & 0xFFFF
    rd = instr & 0x1F
    return rd, imm16, hw * 16


def find_service_name(text: bytes, wanted: str, reg: int = 1):
    """在 text 里找能把 wanted 拼进寄存器 reg 的指令序列

    返回 (成功?, 还原出的名字)。逐条扫描 MOVZ 作为起点，
    往后最多看 4 条指令收集同寄存器的 MOVK。
    """
    target = int.from_bytes(wanted.encode() + b"\x00" * (8 - len(wanted)),
                            "little")
    n = len(text) // 4

    for i in range(n):
        instr = struct.unpack_from("<I", text, i * 4)[0]
        p = _movz_movk_parts(instr)
        if not p:
            continue
        rd, imm16, shift = p
        if rd != reg:
            continue
        # 从这条指令开始，收集同寄存器的片段
        val = 0
        got = []
        for k in range(6):
            j = i + k
            if j >= n:
                break
            ins = struct.unpack_from("<I", text, j * 4)[0]
            pp = _movz_movk_parts(ins)
            if not pp or pp[0] != reg:
                # 不是同寄存器的 MOVZ/MOVK 就跳过（可能是别的指令）
                continue
            _, im, sh = pp
            val |= im << sh
            got.append((im, sh))
            if val == target:
                raw = val.to_bytes(8, "little")
                name = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
                return True, name, got
    return False, None, []


def verify(nro_or_elf_bytes: bytes, wanted: str, text_offset: int = None,
           text_size: int = None):
    """在给定字节流（或其 .text 段）里验证服务名"""
    if text_offset is not None and text_size is not None:
        text = nro_or_elf_bytes[text_offset:text_offset + text_size]
    else:
        text = nro_or_elf_bytes
    ok, name, parts = find_service_name(text, wanted)
    return ok, name, parts
