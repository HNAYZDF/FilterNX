#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_registry.py — 检查 SD 卡上的 Ultrahand 注册表 overlays.ini

═══════════════════════════════════════════════════════════════════════════
为什么需要这个检查（我漏掉的盲区）
═══════════════════════════════════════════════════════════════════════════
Ultrahand 显示的名字与版本有**两层来源**（Ultrahand-Overlay 源码）:

    source/utils.hpp:953  getOverlayInfo()  读 .ovl 里的 NACP
        → overlayName / overlayVersion

    source/main.cpp:6894-6898
        assignedName    = !customName.empty()    ? customName    : overlayName;
        assignedVersion = !customVersion.empty() ? customVersion : overlayVersion;
        （customName/customVersion 来自 config/ultrahand/overlays.ini）

也就是说 **overlays.ini 里的 custom_* 非空时会压过 NACP**。

我之前的 check_version.py 只查了 .ovl 文件本身，**从没查注册表** ——
于是出现过这种自相矛盾的现场:
    菜单列表显示  6.0.0   （注册表里的旧 custom_version）
    点进插件显示  v1.0.0  （文件里新的 NACP）
两边都"验证通过"，但用户看到的版本是错的。

═══════════════════════════════════════════════════════════════════════════
本脚本检查什么
═══════════════════════════════════════════════════════════════════════════
  1. 注册表里是否存在旧文件名（FilterNX.ovl / 超能滤镜.ovl）的残留段
  2. 每个段里的 custom_name / custom_version 是否与对应 .ovl 的 NACP 一致
  3. 是否存在"有段但没文件"的孤儿段
  4. 是否存在"有文件但段里 custom_* 与 NACP 不符"的冲突（就是本次的 bug）

用法:
    check_registry.py <SD卡根目录>
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nacp_layout import find_nacp, get_name, get_version  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 历史上用过的、现在不该存在的中文/旧文件名
OBSOLETE_NAMES = ["FilterNX.ovl", "超能滤镜.ovl"]


def parse_ini(text: str):
    """返回 [(段名, {键: 值})]，保持文件顺序"""
    out = []
    cur = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            cur = (m.group(1), {})
            out.append(cur)
            continue
        if cur is not None and "=" in s:
            k, v = s.split("=", 1)
            cur[1][k.strip()] = v.strip()
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    sd = Path(sys.argv[1])
    ini_path = sd / "config" / "ultrahand" / "overlays.ini"
    ovl_dir = sd / "switch" / ".overlays"

    print("=== Ultrahand 注册表检查 ===")
    print(f"  SD 卡 : {sd}")
    print(f"  注册表: {ini_path}")
    print()

    if not ini_path.is_file():
        print("  （注册表不存在 —— Ultrahand 首次进插件页时会自建，不算错误）")
        return 0

    raw = ini_path.read_bytes()
    # overlays.ini 是 UTF-8；容错：失败时按 latin-1 读（仅用于结构检查）
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        print("  ⚠ 注册表不是合法 UTF-8（可能被某个编辑器改写成了 GBK）")

    sections = parse_ini(text)
    by_name = {n: kv for n, kv in sections}

    failures = 0

    # ── 1. 旧文件名的残留段 ──
    #
    # 残留段本身就是问题（哪怕 custom_* 为空）:
    #   · 非空的 custom_* 会压过 NACP → 菜单显示旧值（"菜单 6.0.0 / 插件内 1.0.0"）
    #   · 段里的 key_combo 仍会被注册，按下会尝试启动不存在的文件
    #   · 旧段在设置界面里看不见，只能手改
    # 所以这里必须计入 failures，否则检查器会"报告了问题却仍然通过"。
    print("  ── 旧文件名残留 ──")
    found_obsolete = False
    for old in OBSOLETE_NAMES:
        if old in by_name:
            found_obsolete = True
            failures += 1
            exists = (ovl_dir / old).is_file()
            print(f"    ★ 存在 [{old}] 段，对应文件{'存在' if exists else '已删除'}")
            cv = by_name[old].get("custom_version", "")
            cn = by_name[old].get("custom_name", "")
            if cv or cn:
                print(f"        custom_name={cn!r}  custom_version={cv!r}")
                print(f"        ↑ 非空的 custom_* 会**压过 NACP**，"
                      f"菜单会显示这里的值")
            if exists:
                print(f"        ↑ 文件还在，说明旧版没清干净，列表里可能出现两个条目")
    if not found_obsolete:
        print("    [OK] 没有旧文件名残留段")

    # ── 2. 逐个实际存在的 .ovl 检查 custom_* 与 NACP 是否一致 ──
    print()
    print("  ── 各 overlay 的版本一致性（注册表 vs NACP）──")

    ovls = sorted(ovl_dir.glob("*.ovl")) if ovl_dir.is_dir() else []
    if not ovls:
        print("    （找不到 .ovl 文件）")

    for ovl in ovls:
        sec = by_name.get(ovl.name)
        b = ovl.read_bytes()
        off, _, _ = find_nacp(b)
        if off is None:
            nacp_name, nacp_ver = "(无 NACP)", ""
        else:
            nacp_name = get_name(b, off)
            nacp_ver = get_version(b, off)

        if sec is None:
            # 没有段 → 菜单会用 NACP 的值（正常）
            continue

        cn = sec.get("custom_name", "")
        cv = sec.get("custom_version", "")

        # 菜单最终显示的 = custom_* 非空则用它，否则用 NACP
        shown_name = cn if cn else nacp_name
        shown_ver = cv if cv else nacp_ver

        # ═══════════════════════════════════════════════════════════════════
        # 什么才算"问题"—— 判据要精确，否则全是误报
        # ═══════════════════════════════════════════════════════════════════
        #
        # 第一版把"custom_name ≠ NACP 名"也当成冲突，结果在真卡上一口气
        # 报了 3 个**误报**:
        #     emuiibo.ovl       注册表='手办插件'  NACP='emuiibo'
        #     ldn_mitm.ovl      注册表='联机插件'  NACP='ldn_mitm'
        #     WiFi_Switcher.ovl 注册表='无线网络'  NACP=<GBK 乱码>
        #
        # 这三个恰恰是 custom_name 的**正当用途**: 把英文名/乱码名换成
        # 用户看得懂的中文。报成"冲突"是判据错了，不是卡有问题。
        #
        # 真正危险、值得报警的只有一种: **custom_version 与 NACP 版本号
        # 不一致** —— 那会让菜单显示一个过时的版本号，且用户无法从插件
        # 界面察觉。本插件就踩过这个坑（注册表钉着 6.0.0，文件已是 1.0.0）。
        # ═══════════════════════════════════════════════════════════════════

        # ⚠ 只有 NACP 里有**可信**版本号时才能比较。
        #   NACP 版本为空、或不是可打印文本（乱码）时，注册表的值就是唯一来源，
        #   此时不是冲突而是**回退**，应当放行。
        nacp_ver_trusted = bool(nacp_ver) and nacp_ver.isprintable()

        problems = []
        if cv and nacp_ver_trusted and cv != nacp_ver:
            problems.append(
                f"版本不一致 注册表={cv!r} NACP={nacp_ver!r}"
                f"  → 菜单会显示过时的 {cv!r}")

        # 名字被覆盖本身不算问题，但若 NACP 名字**可用**却仍被覆盖，
        # 提示一下（不是失败），方便发现无意的改动。
        name_note = ""
        if cn and nacp_name and nacp_name.isprintable() and cn != nacp_name:
            name_note = f"（名字被改为 {cn!r}，原名 {nacp_name!r} —— 属正常自定义）"

        if problems:
            failures += 1
            print(f"    ★ {ovl.name}")
            for c in problems:
                print(f"        {c}")
            print(f"        → 菜单显示 {shown_name!r} {shown_ver!r}")
        elif cn or cv:
            print(f"    [OK] {ovl.name}  显示 {shown_name!r} {shown_ver!r}{name_note}")

    # ── 3. 孤儿段（有段但没文件）──
    print()
    print("  ── 孤儿段（有设置但文件已不存在）──")
    orphan = 0
    for name, kv in sections:
        if ovl_dir.is_dir() and (ovl_dir / name).is_file():
            continue
        # 已知的历史文件名单独报过，这里不重复
        orphan += 1
        extra = ""
        if kv.get("custom_version"):
            extra = f"  custom_version={kv['custom_version']!r}"
        print(f"    · [{name}]{extra}")
    if orphan == 0:
        print("    [OK] 没有孤儿段")

    print()
    print("=" * 60)
    if failures:
        print(f"结果: ★ {failures} 个 overlay 的注册表版本号与 NACP 不一致")
        print("      菜单显示的会是注册表里的旧版本 —— 这正是"
              "\"菜单 6.0.0 / 插件内 1.0.0\" 的成因")
        print("      修法: 把该段的 custom_version 置空，让菜单跟随 NACP")
        return 1
    print("结果: 注册表与 NACP 一致，菜单显示的版本可信")
    print("      （custom_name 被改成中文属正常自定义，不算冲突）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
