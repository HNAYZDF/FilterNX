#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_ui_lang.py — 确认框架界面文案是中文（不依赖语言文件）

═══════════════════════════════════════════════════════════════════════════
背景
═══════════════════════════════════════════════════════════════════════════
特斯拉菜单底部那一行按键提示（`返回` / `确定` / `隐藏` / `取消`）不是插件
自己画的，是 libultrahand 的 `OverlayFrame` 画的。

它对每个文案维护一个三元组:

    {&变量, "KEY", "英文默认值"}

启动时调 `parseLanguage(jsonFile)` 从语言文件覆盖；
**读不到文件就保留英文默认值**。我的构建没有语言文件，
所以此前一直显示 `Back` / `OK`。

修法: 把默认值直接改成中文（编译进二进制，不依赖外部文件）。
见 tools/patch_libultrahand_lang.py。

本脚本守两件事:
  1. 源码里这些条目确实是中文
  2. **产物里**确实能搜到这些中文（防止改完没重编）
═══════════════════════════════════════════════════════════════════════════
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "third_party" / "libultrahand" / "libultra" / "source" / "tsl_utils.cpp"
OVL = ROOT / "overlay" / "FilterNX.ovl"

# KEY -> 期望的中文
WANT = {
    "OK":                    "确定",
    "BACK":                  "返回",
    "HIDE":                  "隐藏",
    "CANCEL":                "取消",
    "ON":                    "开",
    "OFF":                   "关",
    "UNAVAILABLE_SELECTION": "暂无选项",
    "SYSTEM_RAM":            "系统内存",
    "FREE":                  "剩余",
}

checks = 0
fails = 0


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
    print("=== 框架界面文案汉化核查 ===\n")

    ck(SRC.is_file(), f"找得到 {SRC.name}")
    if not SRC.is_file():
        return 1
    text = SRC.read_text(encoding="utf-8")

    print()
    print("[源码]")
    missing = []
    for key, want in WANT.items():
        m = re.search(
            rf'\{{\s*&\w+\s*,\s*"{re.escape(key)}"\s*,\s*"([^"]*)"\s*\}}', text)
        got = m.group(1) if m else None
        if got == want:
            print(f"  PASS  {key:24} = {got!r}")
        else:
            print(f"  FAIL  {key:24} = {got!r}（期望 {want!r}）")
            missing.append(key)
    ck(not missing, "源码里全部条目都是中文", f"缺: {missing}")

    print()
    print("[产物]")
    ck(OVL.is_file(), f"存在 {OVL.name}")
    if OVL.is_file():
        blob = OVL.read_bytes()
        absent = []
        for key, want in WANT.items():
            # 注意: 单字（开/关）会大量误命中，只检查多字词
            if len(want) < 2:
                continue
            if want.encode("utf-8") in blob:
                print(f"  PASS  产物含 {want!r}")
            else:
                print(f"  FAIL  产物缺 {want!r}")
                absent.append(want)
        ck(not absent,
           "产物里含全部中文界面文案",
           f"缺 {absent} —— 改完 libultrahand 后必须**全量重编**"
           f"（增量编译不会重编库）")

    print()
    print("=" * 60)
    if fails:
        print(f"结果: ★ {fails} 项不通过")
        return 1
    print("结果: 框架界面文案已汉化，且已编入产物")
    return 0


if __name__ == "__main__":
    sys.exit(main())
