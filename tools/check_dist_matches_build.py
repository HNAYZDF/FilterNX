#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_dist_matches_build.py — 确认 dist 里的产物就是「当前构建 + NACP 写入」

═══════════════════════════════════════════════════════════════════════════
为什么不能简单地比 SHA256
═══════════════════════════════════════════════════════════════════════════
overlay/FilterNX.ovl  是**刚构建出来**的裸产物
dist/.../Chaoneng.ovl 是 **同一份 + package.sh 写入的 NACP 名字/版本**

set_nacp.py 是**原地改写**已有字段（不改文件大小），所以两者
SHA256 必然不同 —— 直接比哈希会得出"dist 是旧的"这个**错误结论**。

（我本人就先这么误判了一次，差点去"修"一个并不存在的问题。）

═══════════════════════════════════════════════════════════════════════════
正确的判据
═══════════════════════════════════════════════════════════════════════════
  1. 文件大小相同
  2. **除 NACP 区域外**逐字节相同  → 证明 dist 就是这份构建
  3. NACP 里的名字 / 版本 == 源码里的值  → 证明元数据写对了
  4. 版本号 == version.hpp（唯一来源）
  5. 分发文件名是纯 ASCII（中文文件名大气层无法识别）

这样既能发现"dist 陈旧"，又不会把"正常的 NACP 差异"误判成问题。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nacp_layout import (  # noqa: E402
    find_nacp, get_name, get_version, get_isbn,
    LANG_STRIDE, LANG_COUNT, NAME_OFF, NAME_SIZE,
    AUTHOR_OFF, AUTHOR_SIZE,
    DISPLAY_VERSION_OFF, DISPLAY_VERSION_SIZE,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
BUILD_OVL = ROOT / "overlay" / "FilterNX.ovl"
DIST_OVL = ROOT / "dist" / "switch" / ".overlays" / "Chaoneng.ovl"
VER_HPP = ROOT / "overlay" / "src" / "version.hpp"
GUI = ROOT / "overlay" / "src" / "gui.cpp"

checks = 0
fails = 0


def ck(cond, label, detail=""):
    global checks, fails
    checks += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))
        fails += 1


def main():
    print("=== dist 产物与当前构建一致性 ===\n")

    if not BUILD_OVL.is_file():
        print(f"  [skip] 找不到构建产物 {BUILD_OVL}")
        print("         请先运行 build-overlay.sh")
        return 1

    # 分发文件按 package.sh 的规则推导，不硬编码
    pkg = (ROOT / "package.sh").read_text(encoding="utf-8")
    stem = re.search(r"FILE_STEM='([^']+)'", pkg)
    stem = stem.group(1) if stem else "Chaoneng"
    dist_ovl = ROOT / "dist" / "switch" / ".overlays" / f"{stem}.ovl"

    if not dist_ovl.is_file():
        print(f"  [skip] 找不到分发产物 {dist_ovl}")
        print("         请先运行 package.sh")
        return 1

    build = BUILD_OVL.read_bytes()
    dist = dist_ovl.read_bytes()

    # ── 1. 大小 ──
    print("[文件]")
    print(f"        构建: {BUILD_OVL.name}  {len(build)} 字节")
    print(f"        分发: {dist_ovl.name}  {len(dist)} 字节")
    ck(len(build) == len(dist), "两者大小相同（set_nacp 只改写不增删）",
       f"{len(build)} vs {len(dist)} —— 大小不同说明 dist 不是这份构建")

    if len(build) != len(dist):
        return 1

    # ── 2. 内容比对 ──
    #
    # ⚠ find_nacp 返回 (nacp绝对偏移, aset偏移, 区段列表) —— 不是 (偏移, 尺寸)。
    #   我第一版把它当成 (offset, size) 解包，算出一个 659456 字节的
    #   "NACP 区域"，越界崩溃。这里改成**直接求差异区间**，
    #   比"猜 NACP 多大"更直接也更有说服力。
    print("\n[内容比对]")
    nacp_off, aset_off, sections = find_nacp(dist)
    if nacp_off is None:
        ck(False, "能在产物里定位 NACP", "找不到 NACP，set_nacp 可能没跑")
        return 1
    print(f"        ASET 偏移: 0x{aset_off:X}")
    print(f"        NACP 偏移: 0x{nacp_off:X}")
    print(f"        资源区段 (icon/nacp/romfs): {sections}")

    diff = [i for i in range(len(build)) if build[i] != dist[i]]
    if not diff:
        ck(True, "两份文件完全相同（本构建未写入 NACP 差异）")
    else:
        lo, hi = diff[0], diff[-1]
        print(f"        差异字节数: {len(diff)}")
        print(f"        差异范围  : 0x{lo:X} .. 0x{hi:X}")

        # 允许差异的区域: 16 个语言槽的 name **与 author** + display_version
        #
        # ⚠ author 很容易漏: set_nacp.py 会把名字同时写进每个语言项的
        #   author 字段（16 槽 × 12 字节 = 192 字节）。
        #   我第一版只允许了 name，于是把 192 字节正常写入误报成
        #   "dist 不是这份构建"。允许区域必须与 set_nacp.py 的实际行为一致。
        allowed = []
        for lang in range(LANG_COUNT):
            base_n = nacp_off + lang * LANG_STRIDE + NAME_OFF
            allowed.append((base_n, base_n + NAME_SIZE, f"lang[{lang}].name"))
            base_a = nacp_off + lang * LANG_STRIDE + AUTHOR_OFF
            allowed.append((base_a, base_a + AUTHOR_SIZE, f"lang[{lang}].author"))
        dv = nacp_off + DISPLAY_VERSION_OFF
        allowed.append((dv, dv + DISPLAY_VERSION_SIZE, "display_version"))

        outside = [i for i in diff
                   if not any(a <= i < b for a, b, _ in allowed)]
        ck(not outside,
           "所有差异都落在 NACP 的名字/版本字段内",
           (f"{len(outside)} 字节差异在允许区域之外，"
            f"首个在 0x{outside[0]:X} —— dist 不是这份构建") if outside else "")

        # 报出哪些字段被改了，便于人工确认
        touched = []
        for a, b, label in allowed:
            n = sum(1 for i in diff if a <= i < b)
            if n:
                touched.append(f"{label}({n}字节)")
        print(f"        被写入的字段: {', '.join(touched) if touched else '无'}")

    # ── 3. NACP 元数据 == 源码 ──
    print("\n[NACP 元数据]")
    ver_src = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"',
                        VER_HPP.read_text(encoding="utf-8"), re.M)
    ver_src = ver_src.group(1) if ver_src else None
    ck(ver_src is not None, "能从 version.hpp 读出版本号")

    ver_nacp = get_version(dist, nacp_off)
    name_nacp = get_name(dist, nacp_off)
    print(f"        源码版本 : {ver_src}")
    print(f"        NACP 名字: {name_nacp}")
    print(f"        NACP 版本: {ver_nacp}")

    ck(ver_nacp == ver_src,
       f"NACP 版本与 version.hpp 一致（{ver_src}）",
       f"NACP 是 {ver_nacp}，源码是 {ver_src} —— dist 是旧版本，需重新打包")

    # 作者名 / 群号也能在产物里查到，顺带确认不是旧构建
    gui = GUI.read_text(encoding="utf-8")
    author = re.search(r'ListItem\("作者"\s*,\s*"([^"]+)"\)', gui)
    author = author.group(1) if author else None
    if author:
        ck(author.encode("utf-8") in dist,
           f"产物里含当前作者名 {author}",
           "产物里找不到作者名 —— 可能是改作者名之前构建的")

    # ── 4. isbn 必须为空 ──
    #
    # 曾经把版本号误写进 isbn(0x3000)，菜单读不到 display_version。
    # 这里持续守着，避免回归。
    isbn = get_isbn(dist, nacp_off)
    ck(isbn == "", "isbn 为空（版本号没被误写到这里）",
       f"isbn = {isbn!r}")

    # ── 5. 文件名纯 ASCII ──
    print("\n[分发文件名]")
    ck(dist_ovl.name.isascii(),
       f"文件名是纯 ASCII（{dist_ovl.name}）",
       "中文文件名大气层完全无法识别 —— 插件会不显示")

    # ── 6. 无残留的旧文件名 ──
    ovl_dir = dist_ovl.parent
    others = [p.name for p in ovl_dir.glob("*.ovl") if p.name != dist_ovl.name]
    ck(not others, "分发目录里没有多余的 .ovl",
       f"发现多余文件: {others}")

    print("\n" + "=" * 60)
    print(f"检查项: {checks}   失败: {fails}")
    print("结果: " + ("dist 就是当前构建（元数据已正确写入）" if fails == 0
                     else "★ dist 与当前构建不一致，需重新打包"))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
