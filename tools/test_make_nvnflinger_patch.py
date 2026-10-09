#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_make_nvnflinger_patch.py — 合成 NSO 自测

构造一个含目标 ARM64 指令序列的假 NSO，验证补丁工具能正确定位并生成 IPS。
这是纯离线自测，不需要真实固件。
"""

import ctypes
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from make_nvnflinger_patch import (  # noqa: E402
    NsoHeader, CMU_IOCTL_CODE, PATCH_SEQ, find_cmu_ioctl_call, lz4_decompress_block,
)

HERE = Path(__file__).parent
TOOL = HERE / "make_nvnflinger_patch.py"


def movz(rd: int, imm16: int, shift: int = 0) -> int:
    """MOVZ Xd/Wd, #imm16, LSL #shift"""
    assert rd < 32 and imm16 <= 0xFFFF and shift % 16 == 0
    return (1 << 31) | (0b10 << 29) | (0b100101 << 23) | ((shift // 16) << 21) | (imm16 << 5) | rd


def movk(rd: int, imm16: int, shift: int = 0) -> int:
    """MOVK Xd/Wd, #imm16, LSL #shift"""
    assert rd < 32 and imm16 <= 0xFFFF and shift % 16 == 0
    return (1 << 31) | (0b11 << 29) | (0b100101 << 23) | ((shift // 16) << 21) | (imm16 << 5) | rd


def bl(offset_words: int) -> int:
    """BL #offset (以指令数计)"""
    return 0x94000000 | (offset_words & 0x03FFFFFF)


def nop() -> int:
    return 0xD503201F


def build_text(variant: str, prefix_words: int = 8) -> tuple[bytes, int]:
    """构造 .text，返回 (text, 期望的补丁点偏移)。"""
    words = [nop()] * prefix_words

    if variant == "lo_then_hi":
        # mov w1, #0x20e ; movk w1, #0xc99a, lsl #16 ; ... ; bl
        words.append(movz(1, 0x020E))
        words.append(movk(1, 0xC99A, 16))
    elif variant == "hi_then_lo":
        # mov w1, #0xc99a0000 ; movk w1, #0x20e ; ... ; bl
        words.append(movz(1, 0xC99A, 16))
        words.append(movk(1, 0x020E))
    else:
        raise ValueError(variant)

    words.append(nop())          # 中间夹一条
    words.append(movz(0, 0x0101))  # 无关指令
    words.append(bl(0x100))      # 调用 NvOsDrvIoctl

    patch_off = len(words) * 4   # bl 的下一条
    words.append(nop())          # 补丁点
    words.append(nop())
    words.append(0xD65F03C0)     # ret

    text = b"".join(struct.pack("<I", w) for w in words)
    return text, patch_off


def make_nso(path: Path, text: bytes, module_name: bytes = b"nvnflinger",
             build_id: bytes = bytes(range(0x20))) -> None:
    hdr = NsoHeader()
    ctypes.memset(ctypes.byref(hdr), 0, ctypes.sizeof(hdr))
    hdr.magic = 0x304F534E  # "NSO0"
    hdr.version = 0
    hdr.flags = 0           # 不压缩、不带哈希，简化测试

    text_off = ctypes.sizeof(NsoHeader)
    hdr.text_hdr.file_off = text_off
    hdr.text_hdr.memory_off = 0
    hdr.text_hdr.size = len(text)
    hdr.text_comp_sz = len(text)

    name_off = text_off + len(text)
    hdr.module_name_off = name_off
    hdr.module_name_sz = len(module_name) + 1

    hdr.build_id = (ctypes.c_uint8 * 0x20)(*build_id)

    blob = bytes(hdr) + text + module_name + b"\x00"
    path.write_bytes(blob)


def run_tool(nso: Path, out: Path, extra=None):
    cmd = [sys.executable, str(TOOL), str(nso), "-o", str(out)]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> int:
    failures = []

    def check(cond, label):
        if cond:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}")
            failures.append(label)

    tmp = Path(tempfile.mkdtemp(prefix="fnx_patch_test_"))
    print(f"临时目录: {tmp}\n")

    for variant in ("lo_then_hi", "hi_then_lo"):
        print(f"=== 变体 {variant} ===")
        text, expected_off = build_text(variant)

        # 1. 直接测定位函数
        found = find_cmu_ioctl_call(text)
        check(found == expected_off,
              f"find_cmu_ioctl_call 定位正确 (期望 0x{expected_off:X}, 实际 "
              f"{'None' if found is None else hex(found)})")

        # 2. 端到端跑 CLI
        nso = tmp / f"{variant}.nso"
        out = tmp / f"out_{variant}"
        make_nso(nso, text)
        r = run_tool(nso, out)

        check(r.returncode == 0, f"CLI 退出码为 0 (实际 {r.returncode})")
        if r.returncode != 0:
            print("    stderr:", r.stderr.strip()[:400])

        ips_files = list(out.glob("*.ips")) if out.exists() else []
        check(len(ips_files) == 1, f"生成了 1 个 .ips (实际 {len(ips_files)})")

        if ips_files:
            data = ips_files[0].read_bytes()
            check(data.startswith(b"PATCH"), "IPS 以 PATCH 开头")
            check(data.endswith(b"EOF"), "IPS 以 EOF 结尾")

            off = int.from_bytes(data[5:8], "big")
            ln = int.from_bytes(data[8:10], "big")
            payload = data[10:10 + ln]

            expected_file_off = ctypes.sizeof(NsoHeader) + expected_off
            check(off == expected_file_off,
                  f"IPS 文件偏移正确 (期望 0x{expected_file_off:X}, 实际 0x{off:X})")
            check(ln == len(PATCH_SEQ), f"IPS 长度正确 ({ln})")
            check(payload == PATCH_SEQ, f"IPS 载荷为 mov w0,wzr (实际 {payload.hex()})")

            # 3. 验证补丁真的落在 bl 的下一条上
            patched_off = off - ctypes.sizeof(NsoHeader)
            check(patched_off == expected_off, "补丁点紧跟在 bl 之后")

            # 验证 bl 确实在补丁点的前一条
            prev = struct.unpack_from("<I", text, patched_off - 4)[0]
            check((prev & 0xFC000000) == 0x94000000, "补丁点的前一条确实是 BL")

            # 4. 用该 build_id 命名
            check(ips_files[0].stem.upper() == bytes(range(0x20)).hex().upper(),
                  "IPS 以 build id 命名")
        print()

    # 5. 负例: 不含目标序列时应失败而不是乱打补丁
    print("=== 负例: 无目标序列 ===")
    junk = b"".join(struct.pack("<I", nop()) for _ in range(64))
    nso = tmp / "junk.nso"
    make_nso(nso, junk)
    out = tmp / "out_junk"
    r = run_tool(nso, out)
    check(r.returncode != 0, f"找不到序列时退出码非 0 (实际 {r.returncode})")
    check(not (out.exists() and list(out.glob("*.ips"))), "找不到序列时不生成 .ips")
    print()

    # 6. 负例: 模块名不对时应拒绝
    print("=== 负例: 模块名不匹配 ===")
    text, _ = build_text("lo_then_hi")
    nso = tmp / "wrong.nso"
    make_nso(nso, text, module_name=b"some_other_module")
    out = tmp / "out_wrong"
    r = run_tool(nso, out)
    check(r.returncode == 2, f"模块名不符时返回 2 (实际 {r.returncode})")
    r2 = run_tool(nso, out, extra=["--force"])
    check(r2.returncode == 0, f"--force 可继续 (实际 {r2.returncode})")
    print()

    # 7. LZ4 解压自测
    print("=== LZ4 解压自测 ===")
    # 手工构造: 12 个字面量 "hello world!" 然后结束
    lit = b"hello world!"
    token = (len(lit) << 4)
    block = bytes([token]) + lit
    try:
        got = lz4_decompress_block(block, len(lit))
        check(got == lit, "纯字面量块解压正确")
    except Exception as e:
        check(False, f"纯字面量块解压异常: {e}")

    # 带重叠匹配: "ab" 然后匹配 offset=2 len=6 → "abababab"
    lit2 = b"ab"
    tok2 = (len(lit2) << 4) | 2      # 低 4 位 = match_len - 4 = 2 → len 6
    block2 = bytes([tok2]) + lit2 + struct.pack("<H", 2)
    try:
        got2 = lz4_decompress_block(block2, 8)
        check(got2 == b"abababab", f"重叠匹配解压正确 (实际 {got2!r})")
    except Exception as e:
        check(False, f"重叠匹配解压异常: {e}")
    print()

    print("=" * 60)
    if failures:
        print(f"结果: {len(failures)} 项失败")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("结果: 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
