#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diff_config.py — 逐字段比对 FilterNX 与 Fizeau 的 sysmodule config.json

动机: Fizeau 的 sysmodule 在同一台机器上能加载，我的不能。两者的
NPDM 头部已证实逐字节相同、exefs.nsp 都是合法 PFS0。剩下的差异只可能
来自 config.json 的字段——而 config.json 会被 npdmtool 编译成 NPDM。

这个脚本把两边的字段全部摊开对比，只输出【有差异】的地方，
避免我在几十个字段里肉眼找。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Fizeau 的参照源码放在工作区根的 _ovlres/ 下（与 filternx/ 同级）
REF_ROOT = ROOT.parent


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def norm(v):
    """把十六进制字符串归一成整数，便于比较 0x... 与 0X... """
    if isinstance(v, str) and v.lower().startswith("0x"):
        try:
            return int(v, 16)
        except ValueError:
            return v
    return v


def flat(d, prefix=""):
    """把嵌套字典/列表摊平成 {路径: 值}"""
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(flat(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = norm(d)
    return out


def main():
    mine_p = ROOT / "sysmodule" / "config.json"
    fz_p = REF_ROOT / "_ovlres" / "fizeau" / "config.json"

    if not mine_p.is_file():
        print(f"找不到 {mine_p}")
        return 1
    if not fz_p.is_file():
        print(f"找不到 {fz_p}（需要先从 Fizeau 仓库取 config.json）")
        return 1

    mine = load(mine_p)
    fz = load(fz_p)

    fm, ff = flat(mine), flat(fz)

    keys = sorted(set(fm) | set(ff))

    print("=== 字段差异（只列不同的）===\n")
    ndiff = 0
    for k in keys:
        a, b = fm.get(k, "<缺失>"), ff.get(k, "<缺失>")
        if a != b:
            ndiff += 1
            print(f"  {k}")
            print(f"      FilterNX: {a if not isinstance(a,int) else hex(a)}")
            print(f"      Fizeau  : {b if not isinstance(b,int) else hex(b)}")

    if ndiff == 0:
        print("  (无差异)")
    print(f"\n共 {ndiff} 处差异 / 总字段 {len(keys)}")

    # 单独高亮 syscalls 的差异（这是最可能被内核校验的部分）
    print("\n=== syscalls 差异 ===")
    ms = set()
    fs_ = set()
    for cap in mine.get("kernel_capabilities", []):
        if cap.get("type") == "syscalls":
            ms = set(cap.get("value", {}).keys())
    for cap in fz.get("kernel_capabilities", []):
        if cap.get("type") == "syscalls":
            fs_ = set(cap.get("value", {}).keys())

    only_mine = sorted(ms - fs_)
    only_fz = sorted(fs_ - ms)
    print(f"  我多出的:   {only_mine if only_mine else '(无)'}")
    print(f"  我缺少的:   {only_fz if only_fz else '(无)'}")
    print(f"  数量: 我 {len(ms)} / Fizeau {len(fs_)}")

    # map 能力对比
    print("\n=== map 内核能力差异 ===")
    def maps(cfg):
        r = []
        for cap in cfg.get("kernel_capabilities", []):
            if cap.get("type") == "map":
                v = cap["value"]
                r.append((norm(v["address"]), norm(v["size"]),
                          v.get("is_ro"), v.get("is_io")))
        return sorted(r)

    mm, mf = maps(mine), maps(fz)
    for e in mm:
        tag = "共有" if e in mf else "★仅我有"
        print(f"  {tag}  addr=0x{e[0]:08X} size=0x{e[1]:X} ro={e[2]} io={e[3]}")
    for e in mf:
        if e not in mm:
            print(f"  ★仅Fizeau有  addr=0x{e[0]:08X} size=0x{e[1]:X} ro={e[2]} io={e[3]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
