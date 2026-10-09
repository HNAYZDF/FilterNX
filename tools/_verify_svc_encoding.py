#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证服务名是否真的编入了产物（用 AArch64 立即数编码搜索）"""

import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SVC = "fizeau"

b = Path("filternx/overlay/FilterNX.ovl").read_bytes()

# 编译器把 8 字节字符串装进寄存器时，小端序:
#   "fizeau\0\0" -> 0x00007561657a6966
val = int.from_bytes(SVC.encode() + b"\x00" * (8 - len(SVC)), "little")
print(f"=== 服务名 {SVC!r} 的编码验证 ===")
print(f"  期望的 64 位立即数: 0x{val:016X}")
print()

# AArch64 MOVZ/MOVK 编码: 每条指令携带 16 位立即数
#   MOVZ Xd, #imm16, LSL #shift
#   MOVK Xd, #imm16, LSL #shift
# 我们搜「这 4 个 16 位片段是否都出现在 .text 的指令流里」
frags = [
    (val >> 0) & 0xFFFF,
    (val >> 16) & 0xFFFF,
    (val >> 32) & 0xFFFF,
    (val >> 48) & 0xFFFF,
]
print("  四个 16 位片段:")
for k, f in enumerate(frags):
    if f:
        ch = bytes([(f >> 0) & 0xFF, (f >> 8) & 0xFF])
        print(f"    lsl #{k*16:<3} 0x{f:04X}  = {ch!r}")
    else:
        print(f"    lsl #{k*16:<3} 0x{f:04X}  = (\\0\\0，编译器通常省略)")
print()

# 在 .text 里搜 MOVZ/MOVK 指令: 位模式 1_10_100101_hw_imm16_Rd
# 简化: 只要立即数片段以「指令」形式出现即可（低 21 位含 imm16）
text_start, text_size = struct.unpack_from("<II", b, 0x20)
text = b[text_start:text_start + text_size]
print(f"  在 .text（{len(text):,} 字节）里查找这些立即数:")
all_found = True
for k, f in enumerate(frags):
    if f == 0:
        continue
    # MOVZ/MOVK: [sf][10][100101][hw(2)][imm16(16)][Rd(5)]
    # 立即数在 bit5..20。搜「低 16 位 == f」的 4 字节对齐指令
    found = False
    for off in range(0, len(text) - 4, 4):
        instr = struct.unpack_from("<I", text, off)[0]
        imm16 = (instr >> 5) & 0xFFFF
        opc = (instr >> 23) & 0x7F
        # MOVZ(0x2A/0x52) / MOVK(0x72/0xF2) 的高位特征
        if imm16 == f and opc in (0x2A, 0x52, 0x72, 0x62, 0x32, 0x1A):
            found = True
            break
    mark = "找到" if found else "★ 未找到"
    print(f"    片段 0x{f:04X}: {mark}")

# 结论
print()
raw = b.find(SVC.encode())
print(f"  字节流里连续出现 {SVC!r}: {'是' if raw >= 0 else '否（编译器内联成指令，属正常）'}")
print()
print("  说明: 编译器对短字符串会生成 mov + movk 序列编码进指令，")
print("        因此字节流里**没有连续字符串**是正常的。")
print("        真正的验证是上面「立即数片段是否出现在指令里」。")
