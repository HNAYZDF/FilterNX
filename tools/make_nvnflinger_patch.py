#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FilterNX — 大气层游戏滤镜插件（全中文）

make_nvnflinger_patch.py — 生成 nvnflinger CMU 禁用补丁（exefs IPS）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
这个补丁是做什么的
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
nvnflinger 是系统的显示合成服务，它自己启动或重新初始化显示时，会调用
CMU 的 SetCmu ioctl（io code 0xC99A020E）把色彩配置重置回默认值。
这会把我们的滤镜冲掉——表现为插拔底座、切换分辨率、进出游戏时画面
瞬间恢复原色。

本工具定位 nvnflinger 里那一次 SetCmu 调用，把紧随其后的指令改成
"mov w0, wzr"（返回 0，假装调用成功），从而让这次重置不再生效。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
重要：这个补丁不是必需的
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FilterNX 的 sysmodule 里有一个 100ms 周期的重施线程，会持续比对硬件
CMU 状态并在被改动时自动写回。所以即使不打这个补丁：

  · 滤镜依然正常工作
  · 只是被重置后最多有约 100ms 的画面闪回原色

打上补丁可以把这 100ms 的闪烁也消除掉，属于体验优化。装不上不必纠结。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
为什么需要你自己生成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
exefs 补丁的文件名是目标模块的 build id，内容是对该模块机器码的偏移改写。
nvnflinger 是任天堂的版权代码，不能随插件分发，因此必须针对你自己机器的
固件版本现场生成。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
怎么拿到 nvnflinger.nso
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
方法一（推荐）: 用 Lockpick_RCM 在机器上提取系统模块。
    进入 Lockpick_RCM → "Dump from SysNAND" → 会得到一批 .nso，
    其中 nvnflinger 对应标题 ID 0100000000000003。

方法二: 用 hactool 从固件里解出（需要 prod.keys）:
    hactool -t package3 -k prod.keys --exefsdir=exefs firmware/atmosphere/package3
    # nvnflinger 在程序分区里，通常需要先解 NCA，步骤较繁琐

方法三: 找别人分享的、与你固件版本一致的 nvnflinger.nso。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
用法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python make_nvnflinger_patch.py nvnflinger.nso
    python make_nvnflinger_patch.py nvnflinger.nso -o ./out

输出一个名为 <build_id>.ips 的文件。安装位置（二选一）:

    SD:/atmosphere/exefs_patches/nvnflinger_cmu/<build_id>.ips
    SD:/atmosphere/contents/0100000000000003/exefs_patches/<build_id>.ips

推荐后者: 只作用于 nvnflinger 这一个模块，不会和别的补丁目录混淆。

本工具零第三方依赖（不需要 capstone / lz4），只用 Python 标准库。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import struct
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────── 常量

# nvnflinger 的标题 ID
NVNFLINGER_TITLE_ID = "0100000000000003"

# CMU SetCmu 的 ioctl code
#   type = 2 (nvdisp), nr = 14, dir = WRITE, size = 2458
#   编码结果 = 0xC99A020E
CMU_IOCTL_CODE = 0xC99A020E

# 目标模块名（用于在解出来的文件里确认没拿错）
EXPECTED_MODULE_NAME = b"nvnflinger"

# 补丁写入的指令: mov w0, wzr  (= 返回 0)
PATCH_SEQ = b"\xe0\x03\x1f\x2a"


# ─────────────────────────────────────────────────────────── NSO 头

class NsoHeader(ctypes.Structure):
    """NSO0 头，固定 0x100 字节。"""

    TextCompress   = 1 << 0
    RodataCompress = 1 << 1
    DataCompress   = 1 << 2
    TextHash       = 1 << 3
    RodataHash     = 1 << 4
    DataHash       = 1 << 5

    class SegmentHeader(ctypes.Structure):
        _fields_ = [
            ("file_off",   ctypes.c_uint32),
            ("memory_off", ctypes.c_uint32),
            ("size",       ctypes.c_uint32),
        ]

    class SegmentHeaderRelative(ctypes.Structure):
        _fields_ = [
            ("offset", ctypes.c_uint32),
            ("size",   ctypes.c_uint32),
        ]

    _fields_ = [
        ("magic",           ctypes.c_uint32),
        ("version",         ctypes.c_uint32),
        ("reserved1",       ctypes.c_uint32),
        ("flags",           ctypes.c_uint32),
        ("text_hdr",        SegmentHeader),
        ("module_name_off", ctypes.c_uint32),
        ("rodata_hdr",      SegmentHeader),
        ("module_name_sz",  ctypes.c_uint32),
        ("data_hdr",        SegmentHeader),
        ("bss_sz",          ctypes.c_uint32),
        ("build_id",        ctypes.c_uint8 * 0x20),
        ("text_comp_sz",    ctypes.c_uint32),
        ("rodata_comp_sz",  ctypes.c_uint32),
        ("data_comp_sz",    ctypes.c_uint32),
        ("reserved2",       ctypes.c_uint8 * 0x1c),
        ("api_info_hdr",    SegmentHeaderRelative),
        ("dynstr_info_hdr", SegmentHeaderRelative),
        ("dynsym_info_hdr", SegmentHeaderRelative),
        ("text_hash",       ctypes.c_uint8 * 0x20),
        ("rodata_hash",     ctypes.c_uint8 * 0x20),
        ("data_hash",       ctypes.c_uint8 * 0x20),
    ]


assert ctypes.sizeof(NsoHeader) == 0x100, "NSO 头必须是 0x100 字节"


# ─────────────────────────────────────────────────────────── 简易 LZ4 解压

def lz4_decompress_block(src: bytes, uncompressed_size: int) -> bytes:
    """
    解压 LZ4 block 格式（NSO 用的是裸 block，没有 frame 头）。

    只实现解压路径，约 40 行，避免为一个小工具引入 lz4 依赖。
    格式参考: https://github.com/lz4/lz4/blob/dev/doc/lz4_Block_format.md
    """
    dst = bytearray()
    i = 0
    n = len(src)

    while i < n:
        token = src[i]
        i += 1

        # 高 4 位 = 字面量长度
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                if i >= n:
                    raise ValueError("LZ4 数据损坏: 字面量长度越界")
                extra = src[i]
                i += 1
                lit_len += extra
                if extra != 255:
                    break

        if lit_len:
            if i + lit_len > n:
                raise ValueError("LZ4 数据损坏: 字面量超出输入范围")
            dst += src[i:i + lit_len]
            i += lit_len

        if i >= n:
            break  # 到达末尾，正常结束

        # 2 字节小端偏移
        if i + 2 > n:
            raise ValueError("LZ4 数据损坏: 缺少匹配偏移")
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError("LZ4 数据损坏: 匹配偏移为 0")

        # 低 4 位 = 匹配长度 - 4
        match_len = token & 0x0F
        if match_len == 15:
            while True:
                if i >= n:
                    raise ValueError("LZ4 数据损坏: 匹配长度越界")
                extra = src[i]
                i += 1
                match_len += extra
                if extra != 255:
                    break
        match_len += 4

        start = len(dst) - offset
        if start < 0:
            raise ValueError("LZ4 数据损坏: 匹配位置为负")

        # 逐字节复制: 允许重叠（这是 LZ4 的 RLE 用法）
        for k in range(match_len):
            dst.append(dst[start + k])

    if len(dst) != uncompressed_size:
        raise ValueError(
            f"LZ4 解压长度不符: 得到 {len(dst)}，期望 {uncompressed_size}"
        )
    return bytes(dst)


# ─────────────────────────────────────────────────────────── ARM64 指令解码
#
# 这里刻意不做完整反汇编，只精确识别我们关心的几条指令的位模式。
# 好处是零依赖、行为完全可预测；坏处是覆盖范围窄——但这正是我们想要的：
# 一旦遇到没预期的编码，就明确报错，而不是猜。

def _is_movz_or_movn(word: int, rd: int) -> tuple[bool, int, int]:
    """
    识别 MOVZ / MOVN 到寄存器 rd。
    返回 (匹配, 立即数(未移位), 左移位数)。

    MOVZ: sf=1 opc=10 100101 hw(2) imm16(16) Rd(5)
    MOVN: sf=1 opc=00 100101 hw(2) imm16(16) Rd(5)
    """
    if (word >> 24) & 0xFF not in (0xD2, 0xD3, 0x92, 0x93, 0x12, 0x13, 0x52, 0x53):
        # 更精确的判断放到下面
        pass

    # sf(1)=1, opc(2), 100101(6), hw(2), imm16(16), Rd(5)
    if (word & 0x7F800000) != 0x52800000 and (word & 0x7F800000) != 0x12800000:
        return (False, 0, 0)

    sf = (word >> 31) & 1
    if sf != 1:
        return (False, 0, 0)

    opc = (word >> 29) & 0x3
    if opc not in (0b00, 0b10):  # MOVN / MOVZ
        return (False, 0, 0)

    this_rd = word & 0x1F
    if this_rd != rd:
        return (False, 0, 0)

    hw = (word >> 21) & 0x3
    imm16 = (word >> 5) & 0xFFFF
    return (True, imm16, hw * 16)


def _is_orr_mov_reg(word: int, rd: int, rm: int) -> bool:
    """
    识别 "MOV Rd, Rm" 的寄存器形式，即 ORR Rd, WZR, Rm。
    ORR (shifted register): sf=0 opc=01 01010 shift(2) 0 Rm(5) imm6(6) Rn(5) Rd(5)
    当 Rn == 31 (WZR) 且无移位时，汇编写作 MOV Rd, Rm。
    """
    if (word & 0x7FE0FFE0) != 0x2A0003E0:
        return False
    this_rd = word & 0x1F
    rn = (word >> 5) & 0x1F
    this_rm = (word >> 16) & 0x1F
    shift = (word >> 22) & 0x3
    imm6 = (word >> 10) & 0x3F
    return this_rd == rd and rn == 31 and this_rm == rm and shift == 0 and imm6 == 0


def _is_bl(word: int) -> bool:
    """BL: 100101 imm26"""
    return (word & 0xFC000000) == 0x94000000


def _is_movz_movk_any(word: int, rd: int) -> tuple[bool, str, int, int]:
    """
    识别写入 rd 的 MOVZ / MOVK，返回 (匹配, 类型, imm16, 左移位数)。
    用于追踪 "把 ioctl code 拼进 w1" 的过程。
    """
    # 兼容 32 位与 64 位形式，这里只关心 W 寄存器
    if (word & 0x7F800000) == 0x52800000:      # MOVZ (32/64)
        pass
    elif (word & 0x7F800000) == 0x72800000:    # MOVK (32/64)
        pass
    else:
        return (False, "", 0, 0)

    this_rd = word & 0x1F
    if this_rd != rd:
        return (False, "", 0, 0)

    hw = (word >> 21) & 0x3
    imm16 = (word >> 5) & 0xFFFF
    kind = "movz" if (word & 0x7F800000) == 0x52800000 else "movk"
    return (True, kind, imm16, hw * 16)


# ─────────────────────────────────────────────────────────── 查找补丁点

def find_cmu_ioctl_call(text: bytes) -> int | None:
    """
    在 .text 中定位 nvnflinger 重置 CMU 的那次调用。

    目标机器码序列（两种常见形态）:

        mov  w1, #0x20e
        movk w1, #0xc99a, lsl #16
        ...
        bl   NvOsDrvIoctl
        <-- 补丁点（把这条改成 mov w0, wzr）

        mov  w1, #0xc99a0000
        movk w1, #0x20e
        ...
        bl   NvOsDrvIoctl

    返回补丁点的字节偏移，找不到返回 None。
    """
    n = len(text)
    i = 0

    while i + 4 <= n:
        word = struct.unpack_from("<I", text, i)[0]

        # 第一个线索: 往 w1 写 0x20e 或 0xc99a0000
        m, kind, imm16, shift = _is_movz_movk_any(word, rd=1)
        if m and kind == "movz":
            first_ok = (imm16 == 0x020E) or (imm16 == 0xC99A and shift == 16)

            if first_ok:
                # 往后找同一函数的第二条 movz/movk（拼高半/低半）
                forwarded = 0
                j = i + 4
                while j + 4 <= n and forwarded < 16:
                    w2 = struct.unpack_from("<I", text, j)[0]
                    m2, kind2, imm2, shift2 = _is_movz_movk_any(w2, rd=1)

                    if m2 and kind2 in ("movz", "movk"):
                        second_ok = (
                            (imm2 == 0xC99A and shift2 == 16) or
                            (imm2 == 0x020E)
                        )
                        if second_ok:
                            # 再往后找这一次的 bl
                            k = j + 4
                            hops = 0
                            while k + 4 <= n and hops < 32:
                                w3 = struct.unpack_from("<I", text, k)[0]
                                if _is_bl(w3):
                                    target = k + 4  # 补丁点: bl 的下一条
                                    if target + 4 <= n:
                                        return target
                                    return None
                                # 允许指令间夹少量无关指令，但不跨太远
                                hops += 1
                                k += 4
                    forwarded += 1
                    j += 4
        i += 4

    return None


# ─────────────────────────────────────────────────────────── 主流程

def build_patch(text_file_offset_based: int, text_size: int, text: bytes) -> bytes:
    """
    生成 IPS 补丁内容。

    IPS 格式:
        "PATCH"
        偏移(3 字节, 大端) 长度(2 字节, 大端) 数据...
        "EOF"

    偏移是相对于 exefs 中 main 文件（即 NSO）开头的偏移。
    NSO 头部固定 0x100 字节，.text 段的文件偏移由 text_hdr.file_off 给出，
    因此文件内偏移 = text_hdr.file_off + .text 内偏移。
    """
    off = find_cmu_ioctl_call(text)
    if off is None:
        return b""

    file_offset = text_file_offset_based + off

    patch = b"PATCH"
    patch += file_offset.to_bytes(3, byteorder="big")
    patch += len(PATCH_SEQ).to_bytes(2, byteorder="big")
    patch += PATCH_SEQ
    patch += b"EOF"
    return patch, file_offset, off


def load_nso_text(path: Path):
    """读取 NSO，返回 (header, text 字节, 模块名)。必要时解压 text 段。"""
    with path.open("rb") as fp:
        hdr = NsoHeader()
        raw = fp.read(ctypes.sizeof(NsoHeader))
        if len(raw) != ctypes.sizeof(NsoHeader):
            raise ValueError("文件太小，不是有效的 NSO")
        ctypes.memmove(ctypes.byref(hdr), raw, ctypes.sizeof(NsoHeader))

        if hdr.magic != 0x304F534E:  # "NSO0"
            raise ValueError(
                f"magic 不是 NSO0 (读到 0x{hdr.magic:08X})。"
                "如果这是 NCA/NSP，请先用 hactool 解出 exefs 里的 main。"
            )

        # 模块名
        module_name = b""
        if hdr.module_name_sz > 1:
            fp.seek(hdr.module_name_off)
            module_name = fp.read(hdr.module_name_sz).rstrip(b"\x00")

        # .text
        fp.seek(hdr.text_hdr.file_off)
        text = fp.read(hdr.text_comp_sz)

    if hdr.flags & NsoHeader.TextCompress:
        print(f"  .text 是压缩的，正在解压（{len(text)} → {hdr.text_hdr.size} 字节）...")
        text = lz4_decompress_block(text, hdr.text_hdr.size)

    if len(text) != hdr.text_hdr.size:
        raise ValueError(
            f".text 长度异常: 得到 {len(text)}，头里声明 {hdr.text_hdr.size}"
        )

    if hdr.flags & NsoHeader.TextHash:
        if hashlib.sha256(text).digest() != bytes(hdr.text_hash):
            raise ValueError(".text 的 SHA256 与头里的哈希不符，文件可能损坏")

    return hdr, text, module_name


def main() -> int:
    ap = argparse.ArgumentParser(
        description="生成 nvnflinger CMU 禁用补丁（exefs IPS）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("nso", type=Path, help="nvnflinger 的 NSO 文件")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="输出目录（默认与输入文件同目录）")
    ap.add_argument("--force", action="store_true",
                    help="模块名不匹配时仍然继续")
    args = ap.parse_args()

    if not args.nso.is_file():
        print(f"错误: 找不到文件 {args.nso}", file=sys.stderr)
        return 1

    print(f"读取 {args.nso}")
    try:
        hdr, text, module_name = load_nso_text(args.nso)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    build_id = bytes(hdr.build_id).rstrip(b"\x00").hex().upper()
    print(f"  模块名  : {module_name.decode(errors='replace') or '(未命名)'}")
    print(f"  build id: {build_id}")
    print(f"  .text   : {hdr.text_hdr.size} 字节 @ 文件偏移 0x{hdr.text_hdr.file_off:X}")

    # 交叉验证拿对了文件
    if module_name and EXPECTED_MODULE_NAME not in module_name.lower():
        msg = (f"警告: 模块名 '{module_name.decode(errors='replace')}' "
               f"看起来不是 nvnflinger")
        if not args.force:
            print(f"{msg}\n  如果确认无误，加 --force 继续。", file=sys.stderr)
            return 2
        print(msg)

    print("定位 CMU SetCmu 调用点 ...")
    result = build_patch(hdr.text_hdr.file_off, hdr.text_hdr.size, text)

    if not result:
        print(
            "\n未找到目标指令序列。\n"
            "可能原因:\n"
            "  · 这个 nvnflinger 版本的编译结果与预期不同（换了编译器/优化等级）\n"
            "  · 拿到的不是 nvnflinger\n"
            "  · 该固件版本本来就不重置 CMU\n"
            "\n这不影响 FilterNX 正常使用——重施线程会在 100ms 内自动纠正。\n",
            file=sys.stderr,
        )
        return 3

    patch, file_offset, text_off = result
    print(f"  找到调用点: .text + 0x{text_off:X}  →  文件偏移 0x{file_offset:X}")
    print("  补丁内容: bl 之后的指令改为 'mov w0, wzr'（返回 0）")

    out_dir = args.out or args.nso.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{build_id}.ips"
    out_path.write_bytes(patch)

    print(f"\n已生成: {out_path}  ({len(patch)} 字节)")
    print("\n安装方法 — 把该 .ips 放到 SD 卡的:")
    print(f"    /atmosphere/contents/{NVNFLINGER_TITLE_ID}/exefs_patches/{build_id}.ips")
    print("然后重启机器。")
    print("\n提示: 这个补丁只影响 CMU 重置，不改动其它任何行为；")
    print("      删掉该文件即可完全恢复。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
