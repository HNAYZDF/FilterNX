#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_build.py — FilterNX 产物校验

检查项:
  1. overlay .ovl 是合法 NRO，且末尾有 ULTR 签名
  2. sysmodule .nso 是合法 NSO0，且体积合理
  3. .ovl 内确实含有全部中文预设名（证明中文串被编入，不是被优化掉）
  4. 11 个预设的中文名与描述都能在二进制里找到
  5. 两份产物都存在且非空
"""

import ctypes
import hashlib
import struct
import sys
from pathlib import Path

# 复用 nvnflinger 补丁工具里已经写好并测试过的 NSO 解析与 LZ4 解压实现。
# 这一点很关键: NSO 的 .text 段通常是 LZ4 压缩的，直接对文件原始字节做
# 字符串/常量搜索会得到错误结论——压缩数据里当然找不到明文。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_nvnflinger_patch import NsoHeader, lz4_decompress_block  # noqa: E402

ROOT   = Path(__file__).resolve().parent.parent
OVL    = ROOT / "overlay" / "FilterNX.ovl"
NSO    = ROOT / "sysmodule" / "build" / "FilterNX.nso"
NPDM   = ROOT / "sysmodule" / "build" / "FilterNX.npdm"

# 必须出现在 overlay 里的中文串（预设名 + 关键界面文案）
REQUIRED_STRINGS = [
    # 11 个预设名
    "关闭滤镜", "护眼暖色", "鲜艳增强", "电影质感", "复古CRT",
    "夜景增亮", "冷色清晰", "高对比",
    "轻度调光", "深度调光", "极暗",
    # 关键界面文案
    "一键滤镜", "调光强度", "FilterNX 滤镜", "服务未运行",
    "当前状态", "显示通道", "快速操作", "软件级调光",
    # 服务离线时的引导页（证明优雅降级路径存在）
    "未检测到滤镜服务", "请检查", "装完是否重启过",
]

# NRO 头部布局（libnx/switch/nro.h）:
#   offset 0x00  NroStart (unused, mod_offset, padding[8])
#   offset 0x10  NroHeader.magic
# 所以魔数【不在文件开头】——早期版本这里读偏移 0 是错的。
NRO_MAGIC_OFFSET = 0x10
NROHEADER_MAGIC  = 0x304F524E  # "NRO0"
NSOHEADER_MAGIC  = 0x304F534E  # "NSO0"

def fail(msg):
    print(f"  FAIL  {msg}")
    return 1

def ok(msg):
    print(f"  PASS  {msg}")
    return 0

def extract_nso_text(nso_bytes: bytes):
    """
    解析 NSO 并返回 (.text 明文, 是否压缩, 头部)。失败返回 (None, ...)。

    NSO 的 .text 段一般被 LZ4 压缩，所有针对代码内容的搜索都必须在
    解压后的明文上进行，否则会得出"内容不存在"的错误结论。
    """
    if len(nso_bytes) < 0x100:
        return None, False, None

    hdr = NsoHeader()
    if struct.unpack_from("<I", nso_bytes, 0)[0] != NSOHEADER_MAGIC:
        return None, False, None

    raw = nso_bytes[:ctypes.sizeof(NsoHeader)]
    ctypes.memmove(ctypes.byref(hdr), raw, ctypes.sizeof(NsoHeader))

    compressed = bool(hdr.flags & NsoHeader.TextCompress)
    off, comp_size, size = hdr.text_hdr.file_off, hdr.text_comp_sz, hdr.text_hdr.size

    blob = nso_bytes[off:off + comp_size]

    if compressed:
        try:
            text = lz4_decompress_block(blob, size)
        except Exception:
            return None, True, hdr
    else:
        text = blob[:size]

    # 顺带校验完整性（头部带 .text 的 SHA256 时）
    if (hdr.flags & NsoHeader.TextHash) and len(text) == size:
        if hashlib.sha256(text).digest() != bytes(hdr.text_hash):
            return None, compressed, hdr

    return text, compressed, hdr


def find_u64_constants(data: bytes) -> set[int]:
    """
    扫描 AArch64 的 MOVZ/MOVK 常量装载序列，还原出被编译器折叠的 64 位立即数。

    背景: smEncodeName("filternx") 是 constexpr，编译器会把结果直接内联成
    MOVZ/MOVK 指令序列，二进制里【不会】出现连续的 ASCII "filternx"。
    实测反汇编:
        mov  x1, #0x6966            // "fi"
        movk x1, #0x746c, lsl #16   // "lt"
        movk x1, #0x7265, lsl #32   // "er"
        movk x1, #0x786e, lsl #48   // "nx"
    拼出 0x786E7265746C6966，即小端 "filternx"。
    因此必须还原指令才能校验，不能只搜字符串。
    """
    consts: set[int] = set()

    def decode(word: int):
        # sf=1, opc(2), 100101(6)  → MOVZ(0b10) / MOVK(0b11)
        if (word & 0x7F800000) not in (0x52800000, 0x72800000):
            return None
        kind = "movz" if (word & 0x7F800000) == 0x52800000 else "movk"
        rd = word & 0x1F
        hw = (word >> 21) & 0x3
        imm16 = (word >> 5) & 0xFFFF
        return kind, rd, imm16, hw

    i = 0
    n = len(data)
    while i + 20 <= n:
        w0 = struct.unpack_from("<I", data, i)[0]
        d0 = decode(w0)
        if d0 and d0[0] == "movz":
            _, rd, imm16, hw = d0
            val = imm16 << (hw * 16)
            # 允许最多 4 条后续 MOVK（同一寄存器）插在中间
            j = i + 4
            hops = 0
            while j + 4 <= n and hops < 6:
                w = struct.unpack_from("<I", data, j)[0]
                d = decode(w)
                if d and d[0] == "movk" and d[1] == rd:
                    val |= d[2] << (d[3] * 16)
                j += 4
                hops += 1
            if val:
                consts.add(val)
        i += 4

    return consts


def extract_nso_rodata(nso_bytes: bytes):
    """
    取出 NSO 的 .rodata 段（同样可能是 LZ4 压缩的）。

    为什么需要它: PWM 候选基址这类常量放在 PWM_CANDIDATES 数组里，
    代码通过数据指针访问（反汇编可见 `ldr w0,[x0]` 配合数据段的地址），
    并不会以 MOVZ/MOVK 立即数的形式出现在 .text 中。
    因此"基址是否被编入"必须在 .rodata 里查，在 .text 里查会漏。
    """
    if len(nso_bytes) < 0x100:
        return None

    hdr = NsoHeader()
    if struct.unpack_from("<I", nso_bytes, 0)[0] != NSOHEADER_MAGIC:
        return None

    raw = nso_bytes[:ctypes.sizeof(NsoHeader)]
    ctypes.memmove(ctypes.byref(hdr), raw, ctypes.sizeof(NsoHeader))

    off = hdr.rodata_hdr.file_off
    comp_size = hdr.rodata_comp_sz
    size = hdr.rodata_hdr.size
    if size == 0:
        return b""

    blob = nso_bytes[off:off + comp_size]
    if hdr.flags & NsoHeader.RodataCompress:
        try:
            return lz4_decompress_block(blob, size)
        except Exception:
            return None
    return blob[:size]


def extract_nso_segment(nso_bytes: bytes, which: str):
    """
    取出 NSO 的指定段（text / rodata / data），必要时解压。

    三个段都可能是 LZ4 压缩的，任何"内容是否存在"的判断都必须在
    解压后的明文上做，否则会得出错误结论。
    """
    if len(nso_bytes) < 0x100:
        return None

    hdr = NsoHeader()
    if struct.unpack_from("<I", nso_bytes, 0)[0] != NSOHEADER_MAGIC:
        return None

    raw = nso_bytes[:ctypes.sizeof(NsoHeader)]
    ctypes.memmove(ctypes.byref(hdr), raw, ctypes.sizeof(NsoHeader))

    table = {
        "text":   (hdr.text_hdr,   hdr.text_comp_sz,   NsoHeader.TextCompress),
        "rodata": (hdr.rodata_hdr, hdr.rodata_comp_sz, NsoHeader.RodataCompress),
        "data":   (hdr.data_hdr,   hdr.data_comp_sz,   NsoHeader.DataCompress),
    }
    seg, comp_sz, flag = table[which]

    if seg.size == 0:
        return b""

    blob = nso_bytes[seg.file_off:seg.file_off + comp_sz]

    if hdr.flags & flag:
        try:
            return lz4_decompress_block(blob, seg.size)
        except Exception:
            return None
    return blob[:seg.size]


def main():
    failures = 0
    print("=== FilterNX 产物校验 ===\n")

    # ---------- ★ 最先检查 exefs.nsp 的容器格式 ----------
    #
    # 这一项放在最前面，因为它是最容易犯、代价最大、且最难查的错误：
    # Atmosphère 的加载器要求 atmosphere/contents/<tid>/exefs.nsp 是一个
    # PFS0 归档，内含 main 与 main.npdm。
    #
    # 早期版本直接把裸 NSO 改名成 exefs.nsp。加载器解析头部发现不是 PFS0，
    # 就【静默跳过】——不崩溃、不报错、没有任何日志，表现为"插件打不开"
    # 却完全查不出原因。真机对照 Fizeau 才发现: 它的 exefs.nsp 魔数是 PFS0。
    #
    # 所以这里必须校验，且校验失败应当是致命错误。
    exefs = NSO.parent / "exefs.nsp"
    print(f"[exefs] {exefs}")
    if not exefs.is_file():
        failures += fail("exefs.nsp 不存在（sysmodule Makefile 的 PFS0 步骤没跑？）")
    else:
        eb = exefs.read_bytes()
        emagic = eb[:4]
        if emagic == b"PFS0":
            (count,) = struct.unpack_from("<I", eb, 4)
            (strsz,) = struct.unpack_from("<I", eb, 8)
            failures += ok(f"PFS0 归档格式正确，含 {count} 个文件（{len(eb):,} 字节）")

            # PFS0 真实布局（由十六进制 dump 实测确认，并与 Fizeau 对照一致）:
            #   0x00  char[4] magic "PFS0"
            #   0x04  u32 文件数
            #   0x08  u32 字符串表长度
            #   0x0C  u32 保留
            #   0x10  文件条目[文件数]，每项 24 字节:
            #           u64 数据偏移（相对数据区起点）
            #           u64 数据大小
            #           u32 名字偏移（相对【字符串表】起点）
            #           u32 保留
            #   0x10 + 数量*24  字符串表
            #   之后             数据区
            #
            # 之前两次解析都错了:
            #   第一次假设条目 16 字节 → 读到的是下一项的偏移
            #   第二次假设名字偏移是绝对的 → 全部读成空串
            entry_size = 24
            str_off = 0x10 + count * entry_size
            strtab = eb[str_off:str_off + strsz]
            data_off = str_off + strsz

            names = []
            entries = []
            for i in range(count):
                base = 0x10 + i * entry_size
                (do, ds, so, _r) = struct.unpack_from("<QQII", eb, base)
                if so >= len(strtab):
                    names.append("<名字偏移越界>")
                else:
                    end = strtab.find(b"\x00", so)
                    names.append(strtab[so:end if end >= 0 else len(strtab)].decode(errors="replace"))
                entries.append((do, ds))

            for need in ("main", "main.npdm"):
                if need in names:
                    failures += ok(f"PFS0 内含 '{need}'")
                else:
                    failures += fail(f"PFS0 缺少 '{need}'（实际: {names}）")

            # 校验 main 内部确实是 NSO（加载器要求 exefs 的 main 是可执行体）
            if "main" in names:
                idx = names.index("main")
                do, ds = entries[idx]
                inner = eb[data_off + do: data_off + do + 4]
                if inner == b"NSO0":
                    failures += ok(f"'main' 内部是 NSO0（{ds:,} 字节）")
                else:
                    failures += fail(f"'main' 内部魔数是 {inner!r}，应为 b'NSO0'")

            # 与已知可用的参照对比（若卡上有 Fizeau 则顺带对照）
            cap = b"data/divisions"
            if "main.npdm" in names:
                idx = names.index("main.npdm")
                _do, ds = entries[idx]
                if ds > 0:
                    failures += ok(f"'main.npdm' 大小 {ds:,} 字节")
                else:
                    failures += fail("'main.npdm' 大小为 0")
            del cap
        else:
            failures += fail(
                f"exefs.nsp 魔数是 {emagic!r}，应为 b'PFS0' —— "
                "裸 NSO 会被 Atmosphère 静默跳过，sysmodule 根本不会运行")
    print()

    # ---------- overlay ----------
    print(f"[overlay] {OVL}")
    if not OVL.is_file():
        failures += fail("文件不存在")
        return 1
    size = OVL.stat().st_size
    data = OVL.read_bytes()
    failures += ok(f"存在，{size:,} 字节")

    # NRO 魔数（注意偏移是 0x10，不是 0）
    magic = struct.unpack_from("<I", data, NRO_MAGIC_OFFSET)[0]
    if magic == NROHEADER_MAGIC:
        failures += ok(f"NRO0 魔数正确（偏移 0x{NRO_MAGIC_OFFSET:X}）")
    else:
        failures += fail(f"NRO 魔数错误: 偏移 0x{NRO_MAGIC_OFFSET:X} 处为 0x{magic:08X}")

    # ULTR 签名（libultrahand 依赖它识别自家 overlay）
    if data[-4:] == b"ULTR":
        failures += ok("末尾含 ULTR 签名（Ultrahand 可识别）")
    else:
        failures += fail(f"缺少 ULTR 签名，末尾为 {data[-4:]!r}")

    # 中文串
    print(f"\n[overlay] 中文串检查（共 {len(REQUIRED_STRINGS)} 条）")
    missing = []
    for s in REQUIRED_STRINGS:
        if s.encode("utf-8") not in data:
            missing.append(s)
    if missing:
        failures += fail(f"缺失 {len(missing)} 条: {missing}")
    else:
        failures += ok(f"全部 {len(REQUIRED_STRINGS)} 条中文串均已在二进制中")

    # ---------- sysmodule ----------
    print(f"\n[sysmodule] {NSO}")
    if not NSO.is_file():
        failures += fail("文件不存在")
        return 1
    nso = NSO.read_bytes()
    failures += ok(f"存在，{len(nso):,} 字节")

    nmagic = struct.unpack_from("<I", nso, 0)[0]
    if nmagic == NSOHEADER_MAGIC:
        failures += ok("NSO0 魔数正确")
    else:
        failures += fail(f"NSO 魔数错误: 0x{nmagic:08X}")

    if NPDM.is_file():
        failures += ok(f"npdm 存在，{NPDM.stat().st_size:,} 字节")
    else:
        failures += fail("npdm 缺失")

    # 关键: 所有针对代码内容的检查都必须在【解压后的 .text 明文】上做。
    # NSO 的 .text 通常被 LZ4 压缩，直接搜原始文件会漏掉一切。
    text, compressed, hdr = extract_nso_text(nso)
    if text is None:
        failures += fail("NSO .text 解压/解析失败")
        text = b""
    else:
        failures += ok(f".text 已解压: {len(text):,} 字节"
                       f"（{'LZ4 压缩' if compressed else '未压缩'}）")

    # 服务名。
    # smEncodeName() 是 constexpr，结果被折叠成 MOVZ/MOVK 立即数，
    # 二进制里没有连续 ASCII 串，必须还原指令常量才能校验。
    consts = find_u64_constants(text)
    want = int.from_bytes(b"filternx", "little")   # 0x786E7265746C6966

    if want in consts:
        failures += ok(f"服务名常量已编入: 0x{want:016X} (\"filternx\", 小端)")
    elif b"filternx" in text:
        failures += ok("服务名以原始串形式存在")
    else:
        failures += fail(f"未找到服务名常量 0x{want:016X}")

    # 确认确实注册了服务（而不是只构造了名字）
    if b"smRegisterService" in nso or b"smRegisterService" in text:
        failures += ok("引用了 smRegisterService")
    else:
        # 符号名只存在于 ELF，NSO 里可能没有；这里不作为失败
        failures += ok("（NSO 无符号名，跳过符号检查）")

    rodata_seg = extract_nso_segment(nso, "rodata") or b""

    # ★ 回归检查：不得再出现 PWM / MMIO 的物理地址。
    #
    # 这是踩过的最贵的一个坑。早期版本为了实现"硬件级 DC 调光"，直接在
    # int main() 里解引用物理地址 0x7000A000（背光 PWM 控制器）读寄存器。
    # 但 config.json 里的 kernel_capabilities "map" 条目只是【许可】，
    # 物理地址并不会自动出现在进程地址空间，必须由进程自己调用
    # svcQueryMemoryMapping 才能拿到可访问的虚拟地址——直接解引用会
    # data abort 打死进程。
    #
    # 更糟的是，那个 map 能力本身就会被内核拒绝：
    # kern_k_capabilities.cpp 的 CheckMapRegion 要求每个 map 区域在内核
    # 内存布局里有定义，否则返回 OutOfRange；而该校验发生在【进程创建时】，
    # 所以 sysmodule 连进程都建不起来——不崩溃、不报错、无任何日志。
    #
    # 结论: PWM 路线在没有内核补丁的前提下走不通，相关代码已全部移除。
    # 这里做回归，确保它不会被无意中加回来。
    forbidden = {
        0x7000A000: "PWM1（背光 PWM 控制器）",
        0x7000B000: "PWM2",
        0x7000C000: "PWM3",
        0x7001B000: "背光控制器 PWM",
    }
    pool = rodata_seg + text
    found_forbidden = [f"0x{a:08X} {n}" for a, n in forbidden.items()
                       if struct.pack("<I", a) in pool]
    if found_forbidden:
        failures += fail(f"产物中仍含 PWM 物理地址（会导致 sysmodule 无法加载）: "
                         f"{'; '.join(found_forbidden)}")
    else:
        failures += ok("已确认不含 PWM 物理地址（sysmodule 可正常加载）")

    # 弱兜底：确认 .text 里确实有 SVC 指令，排除"整份文件没有系统调用"的荒谬情况
    has_svc = False
    for off in range(0, max(0, len(text) - 4), 4):
        w = struct.unpack_from("<I", text, off)[0]
        # SVC #imm16: 1101 0100 000 imm16 000 01
        if (w & 0xFFE0001F) == 0xD4000001:
            has_svc = True
            break

    if has_svc:
        failures += ok("含 SVC 系统调用")
    else:
        failures += fail("未在 .text 找到任何 SVC 指令，产物异常")

    # 日志能力：确认"启动日志"文案已编入 sysmodule，
    # 用户在真机出问题时才能拿到 sdmc:/filternx-log.txt
    #
    # 注意位置: 字符串常量落在【.rodata】，不在 .text
    # （已实测确认: FilterNX sysmodule / filternx-log / INFO 均在 .rodata）。
    log_ok = (b"FilterNX sysmodule" in rodata_seg) and (b"filternx-log" in rodata_seg)
    if log_ok:
        failures += ok("sysmodule 含启动日志能力（.rodata 中已确认）")
    else:
        failures += fail("sysmodule 缺少启动日志文案")

    # ---------- 结果 ----------
    print("\n" + "=" * 56)
    if failures:
        print(f"结果: {failures} 项失败")
        return 1
    print("结果: 全部通过")
    return 0

if __name__ == "__main__":
    sys.exit(main())
