#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_npdm_diff.py — NPDM 与已知可用参照的字节级差异检查

这是本项目最重要的一条验证。

背景: 早期版本的 sysmodule 无法加载（不崩溃、不报错、无日志）。根因是
      kernel_capabilities 里申请了内核不接受的 MMIO map 区域
      （0x7000A000 等），而内核在**进程创建时**校验该能力，失败即拒绝建
      进程（kern_k_capabilities.cpp: CheckMapRegion）。

做法: 用同一版 npdmtool，把 Fizeau 的 config.json 生成一份参照 NPDM，
      再与我的产物逐字节比对。若差异仅限于"模块名"与"program_id"，
      就证明两者的内核能力、syscall 掩码、map 区域完全一致 —— 这是能
      得到的、最强的"应该能加载"证据。

为什么用字节比对而不是解析字段:
      NPDM 的能力是 BitPack32 位域，手工推导编码容易出错（本项目就错过
      一次）。逐字节比对不需要理解编码，且能发现任何遗漏。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_CFG  = ROOT.parent / "_ovlres" / "fizeau" / "config.json"
REF_NPDM = ROOT.parent / "_ovlres" / "fizeau" / "Fizeau.npdm"
MINE     = ROOT / "sysmodule" / "build" / "FilterNX.npdm"
NPDMTOOL = Path("C:/msys64/opt/devkitpro/tools/bin/npdmtool.exe")

# 允许存在差异的区域（只应是名字与 program_id）
ALLOWED_NAME_RANGE = range(0x20, 0x60)      # Acid 头的名称字段
ALLOWED_PID_RANGE  = range(0x280, 0x350)    # Aci0 头的 program_id 等


def build_ref():
    if not REF_CFG.is_file():
        print(f"★ 缺少参照 config.json: {REF_CFG}")
        return False
    if not NPDMTOOL.is_file():
        print(f"★ 缺少 npdmtool: {NPDMTOOL}")
        return False
    subprocess.run([str(NPDMTOOL), str(REF_CFG), str(REF_NPDM)],
                   capture_output=True, text=True)
    return REF_NPDM.is_file()


def main():
    print("=== NPDM 字节级差异检查 ===\n")

    if not MINE.is_file():
        print(f"★ 找不到 {MINE}")
        return 1
    if not build_ref():
        return 1

    mine = MINE.read_bytes()
    ref  = REF_NPDM.read_bytes()

    print(f"  我的   : {MINE.name}  {len(mine):,} 字节")
    print(f"  参照   : Fizeau      {len(ref):,} 字节")
    print()

    if len(mine) != len(ref):
        print(f"★ 长度不同（{len(mine)} vs {len(ref)}），说明字段数量或大小有差异")
        return 1
    print("  长度一致 ✓")
    print()

    # ---- 收集差异 ----
    diffs = [i for i in range(len(mine)) if mine[i] != ref[i]]

    # 归类
    unexpected = [i for i in diffs
                  if i not in ALLOWED_NAME_RANGE and i not in ALLOWED_PID_RANGE]

    print(f"  总差异字节数 : {len(diffs)}")
    print(f"  预期区间内   : {len(diffs) - len(unexpected)}"
          f"  (模块名 + program_id)")
    print(f"  预期区间外   : {len(unexpected)}  ← 应为 0")
    print()

    if unexpected:
        print("★ 在预期之外发现了差异，以下区间需要逐一核对:\n")
        runs = []
        cur = [unexpected[0]]
        for i in unexpected[1:]:
            if i == cur[-1] + 1:
                cur.append(i)
            else:
                runs.append(cur)
                cur = [i]
        runs.append(cur)
        for run in runs:
            s, e = run[0], run[-1]
            mh = " ".join(f"{mine[i]:02x}" for i in run)
            rh = " ".join(f"{ref[i]:02x}" for i in run)
            print(f"  0x{s:04X}..0x{e:04X} ({len(run)} 字节)")
            print(f"      我的  : {mh}")
            print(f"      Fizeau: {rh}")
        print()
        print("=" * 56)
        print("结果: ★ 存在预期外差异 —— 能力集可能已偏离可用配置")
        return 1

    # ---- 展示预期内的差异 ----
    print("  预期内差异明细:")
    runs = []
    cur = [diffs[0]] if diffs else []
    for i in diffs[1:]:
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    if cur:
        runs.append(cur)
    for run in runs:
        s, e = run[0], run[-1]
        mh = " ".join(f"{mine[i]:02x}" for i in run)
        rh = " ".join(f"{ref[i]:02x}" for i in run)
        label = "模块名" if s in ALLOWED_NAME_RANGE else "program_id"
        print(f"    0x{s:04X}..0x{e:04X}  [{label}]")
        print(f"        我的  : {mh}")
        print(f"        Fizeau: {rh}")

    print()
    print("=" * 56)
    print("结果: 全部通过 —— 除模块名与 program_id 外，")
    print("      内核能力 / syscall 掩码 / map 区域与已知可用的")
    print("      Fizeau sysmodule 完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
