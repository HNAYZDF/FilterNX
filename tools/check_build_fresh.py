#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_build_fresh.py — 确认产物比所有源码新（防陈旧 .o 污染产物）

═══════════════════════════════════════════════════════════════════════════
真实事故
═══════════════════════════════════════════════════════════════════════════
我做了一次"临时改服务名为测试字符串 → 构建 → 还原源码"的验证。
还原之后又构建了一次，但 **make 没有重新编译 fizeau_ipc.cpp** ——
因为还原发生在构建之后，.o 比 .hpp 新。

结果: 卡上跑的产物里，服务名一直是那个**测试字符串**，连接当然失败。
而我花了大量时间在别处找原因。

教训: 源码改过之后，**必须确认产物真的比源码新**。
      "构建成功了"不等于"产物包含了最新源码"。
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"
OVL = ROOT / "overlay" / "FilterNX.ovl"
BUILD = ROOT / "overlay" / "build" / "src"

fails = 0
checks = 0


def ck(cond, label, detail=""):
    global checks, fails
    checks += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        if detail:
            print(f"        {detail}")
        fails += 1


def main():
    print("=== 构建新鲜度检查（防陈旧 .o 污染产物）===\n")

    ck(OVL.is_file(), f"存在产物 {OVL.name}")
    if not OVL.is_file():
        return 1

    ovl_t = OVL.stat().st_mtime
    print(f"  产物时间: {_fmt(ovl_t)}")
    print()

    # 1. 每个源文件都必须比产物旧
    print("[源码 vs 产物]")
    newer = []
    for p in sorted(SRC.rglob("*")):
        if p.is_file() and p.suffix in (".cpp", ".hpp", ".h", ".c"):
            if p.stat().st_mtime > ovl_t:
                newer.append(p.name)
                print(f"    ★ {p.name}  {_fmt(p.stat().st_mtime)}  ← 比产物新")
    ck(not newer,
       f"全部源码都不比产物新（共 {len(list(SRC.rglob('*')))} 项）",
       f"比产物新的源码: {newer} —— 需要重新构建")

    # 2. 每个 .o 都必须比它的源文件新
    print()
    print("[目标文件 vs 源文件]")
    stale = []
    if BUILD.is_dir():
        for o in sorted(BUILD.glob("*.o")):
            base = o.name[:-2]                       # 去掉 .o
            for src_p in (SRC / base, ):
                if src_p.is_file() and src_p.stat().st_mtime > o.stat().st_mtime:
                    stale.append(f"{o.name} 比 {src_p.name} 旧")
        # 头文件改动不会单独产生 .o，用整体时间比较
        newest_hpp = max(
            (p.stat().st_mtime for p in SRC.glob("*.hpp")), default=0)
        newest_o = max((o.stat().st_mtime for o in BUILD.glob("*.o")), default=0)
        if newest_hpp > newest_o:
            stale.append(
                f"最新头文件 {_fmt(newest_hpp)} 比最新 .o {_fmt(newest_o)} 新")
    else:
        print("        （没有 build/src 目录，跳过）")

    ck(not stale, "所有 .o 都不比对应源文件旧",
       "; ".join(stale) + " —— make 可能没重新编译")
    print()
    print(f"  产物时间: {_fmt(ovl_t)}")

    print()
    print("=" * 60)
    if fails:
        print(f"结果: ★ {fails} 项不通过 —— 产物可能是陈旧的")
        print("      处理: 删除 overlay/build 后重新构建")
        return 1
    print("结果: 产物比全部源码新，内容可信")
    return 0


def _fmt(t):
    import datetime
    return datetime.datetime.fromtimestamp(t).strftime("%H:%M:%S")


if __name__ == "__main__":
    sys.exit(main())
