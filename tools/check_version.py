#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_version.py — 校验名字与版本在"唯一来源"与产物之间一致

═══════════════════════════════════════════════════════════════════════════
为什么需要这个检查
═══════════════════════════════════════════════════════════════════════════
Ultrahand / Tesla 菜单里显示的 overlay **名字与版本都来自 NACP**
（源码: Ultrahand-Overlay source/utils.hpp:1043-1052 getOverlayInfo()）:

    memchr(nacp.lang_data.lang[0].name, '\0', ...)  → 显示名
    memchr(nacp.display_version, '\0', ...)         → 显示版本

若这两处与 version.hpp 的来源不一致，会出现"界面显示 v6.0.0 但菜单写着
1.0.0"这种自相矛盾，用户报问题时连"他装的到底是哪一版"都判断不了。

⚠ 这个脚本自己也曾有过假通过:
   早期把 display_version 当成 NACP+0x3000（那是 isbn），于是写入与回读
   错得**一致**，校验"通过"却毫无意义。现在偏移统一取自 nacp_layout.py，
   并且额外检查 isbn 是否被误写。

用法:
    check_version.py <分发目录或ovl文件> [version.hpp路径]
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nacp_layout import (  # noqa: E402
    find_nacp, get_name, get_version, get_isbn, MENU_NAME_LANG_INDEX,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_source_version(hpp: Path):
    """从 version.hpp 读出 FNX_VERSION（唯一来源）"""
    text = hpp.read_text(encoding="utf-8")
    m = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"', text, re.M)
    return m.group(1) if m else None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    target = Path(sys.argv[1])
    root = Path(__file__).resolve().parent.parent
    hpp = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "overlay" / "src" / "version.hpp"

    if target.is_dir():
        ovls = list(target.rglob("*.ovl"))
        if not ovls:
            print(f"no .ovl found under {target}")
            return 1
        ovl = ovls[0]
    else:
        ovl = target

    if not hpp.is_file():
        print(f"not found: {hpp}")
        return 1
    if not ovl.is_file():
        print(f"not found: {ovl}")
        return 1

    src_ver = read_source_version(hpp)
    if not src_ver:
        print(f"[FAIL] cannot read FNX_VERSION from {hpp.name}")
        return 1

    b = ovl.read_bytes()
    nacp_off, _, _ = find_nacp(b)

    print("=== 名字 / 版本 一致性检查 ===")
    print(f"  唯一来源 : {hpp.name}  ->  v{src_ver}")
    print(f"  产物     : {ovl.name}")
    print()

    if nacp_off is None:
        print("  [FAIL] NACP not found")
        return 1

    print(f"  NACP 偏移 0x{nacp_off:X}")
    failures = 0

    # ── 1. display_version（菜单右侧显示的版本）──
    got_ver = get_version(b, nacp_off)
    if got_ver == src_ver:
        print(f"  PASS  display_version = {got_ver!r}   (菜单显示的版本)")
    else:
        print(f"  FAIL  display_version = {got_ver!r}, 期望 {src_ver!r}")
        print("        ↑ 菜单里显示的版本就是这个字段")
        failures += 1

    # ── 2. 语言槽 0 的名字（菜单显示的名字）──
    got_name = get_name(b, nacp_off, MENU_NAME_LANG_INDEX)
    if got_name and not got_name.startswith("<非 UTF-8"):
        print(f"  PASS  lang[{MENU_NAME_LANG_INDEX}].name = {got_name!r}   (菜单显示的名字)")
    else:
        print(f"  FAIL  lang[{MENU_NAME_LANG_INDEX}].name 异常: {got_name!r}")
        failures += 1

    # ── 3. 全部 16 个语言槽都应是同一个名字 ──
    names = {get_name(b, nacp_off, i) for i in range(16)}
    if len(names) == 1 and got_name in names:
        print(f"  PASS  全部 16 个语言槽名字一致")
    else:
        print(f"  FAIL  语言槽名字不一致: {sorted(names)}")
        failures += 1

    # ── 4. isbn 应为空（早期版本把版本号误写到这里）──
    isbn = get_isbn(b, nacp_off)
    if not isbn:
        print(f"  PASS  isbn 为空（未被误写）")
    else:
        print(f"  FAIL  isbn 里有内容 {isbn!r} —— 版本号被误写到 isbn 字段了")
        failures += 1

    # ── 5. 界面标题栏里的版本标签（编译进二进制）──
    label = f"v{src_ver}".encode("utf-8")
    if label in b:
        print(f"  PASS  界面版本标签 {label.decode()!r} 已编入产物")
    else:
        print(f"  FAIL  界面里找不到版本标签 {label.decode()!r}")
        failures += 1

    # ── 6. 文件名──
    # 注意: 显示名不来自文件名（那是早期错误结论）。这里只做提示，
    #       不算失败 —— 文件名用中文只是分发时的命名习惯。
    print(f"  ----  文件名 = {ovl.name!r}（仅作分发命名，不决定菜单显示名）")

    print()
    print("=" * 60)
    if failures:
        print(f"结果: ★ {failures} 处不一致")
        return 1
    print(f"结果: 版本 {src_ver} 与名字 {got_name!r} 均已正确写入 NACP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
