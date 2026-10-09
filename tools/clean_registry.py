#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_registry.py — 清理 Ultrahand 注册表（overlays.ini）里的孤儿段

═══════════════════════════════════════════════════════════════════════════
什么是孤儿段
═══════════════════════════════════════════════════════════════════════════
overlays.ini 以 **overlay 文件名**作段名，保存该 overlay 的设置
（星标 / 隐藏 / 优先级 / 启动参数 / 组合键）。

当某个 .ovl 被删掉后，它的段就留了下来 —— 这就是孤儿段。

═══════════════════════════════════════════════════════════════════════════
孤儿段的实际影响（不是"无害的垃圾"）
═══════════════════════════════════════════════════════════════════════════
1. **组合键仍被注册**
   libultrahand 的 loadEntryKeyCombos() 遍历 ini 全部段、拼
   OVERLAY_PATH + fileName，**不检查文件是否存在**。
   按到那个组合键 → 启动不存在的路径 → nx-ovlloader 打开失败 → 退出，
   表现是"组合键没反应 / 菜单弹回来"。

2. **设置界面里看不见**
   设置页按真实文件列表打开，孤儿段只能手改 ini。

所以孤儿段该清。但它也可能是**故意的**（用户打算以后把 overlay 放回来，
想保留设置）—— 因此本脚本默认只**列出**，加 --apply 才真正删除，
并且删除前总是先备份。

用法:
    clean_registry.py <SD卡根目录>            # 只列出，不改动
    clean_registry.py <SD卡根目录> --apply    # 备份后删除孤儿段
"""

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def split_sections(text: str):
    """把 ini 切成 (前导内容, [(段名, 段全文)])，保留原始字节顺序"""
    lines = text.splitlines(keepends=True)

    preamble = []
    sections = []          # [(name, [lines...])]
    cur = None

    for line in lines:
        m = re.match(r"^\s*\[(.+?)\]\s*$", line.rstrip("\n").rstrip("\r"))
        if m:
            cur = (m.group(1), [line])
            sections.append(cur)
        elif cur is None:
            preamble.append(line)
        else:
            cur[1].append(line)

    return preamble, sections


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_changes = "--apply" in sys.argv

    if not args:
        print(__doc__)
        return 1

    sd = Path(args[0])
    ini_path = sd / "config" / "ultrahand" / "overlays.ini"
    ovl_dir = sd / "switch" / ".overlays"

    print("=== Ultrahand 注册表清理 ===")
    print(f"  SD 卡 : {sd}")
    print(f"  注册表: {ini_path}")
    print(f"  模式  : {'删除孤儿段' if apply_changes else '仅列出（不改动）'}")
    print()

    if not ini_path.is_file():
        print("  注册表不存在，无需处理")
        return 0
    if not ovl_dir.is_dir():
        print(f"  ★ 找不到 {ovl_dir}")
        return 1

    raw = ini_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")

    preamble, sections = split_sections(text)

    existing = {p.name for p in ovl_dir.glob("*.ovl")}

    orphans, keepers = [], []
    for name, body in sections:
        # 注册表不存 ovlmenu 自身；若真有该段也一并视为孤儿（它由加载器管理）
        if name in existing:
            keepers.append((name, body))
        else:
            orphans.append((name, body))

    print(f"  段总数    : {len(sections)}")
    print(f"  有效段    : {len(keepers)}")
    print(f"  孤儿段    : {len(orphans)}")
    print()

    if not orphans:
        print("  [OK] 没有孤儿段，无需清理")
        return 0

    print("  ── 孤儿段明细 ──")
    for name, body in orphans:
        keys = {}
        for line in body[1:]:
            if "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
        notes = []
        if keys.get("key_combo"):
            notes.append(f"组合键={keys['key_combo']}（按下会尝试启动不存在的文件）")
        if keys.get("star") == "true":
            notes.append("已星标")
        if keys.get("custom_name"):
            notes.append(f"custom_name={keys['custom_name']}")
        if keys.get("custom_version"):
            notes.append(f"custom_version={keys['custom_version']}")
        if keys.get("hide") == "false":
            notes.append("hide=false")
        suffix = ("   ← " + "；".join(notes)) if notes else ""
        print(f"    · [{name}]{suffix}")

    if not apply_changes:
        print()
        print("  （未做改动。要删除请加 --apply）")
        return 0

    # ── 备份后写回 ──
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = sd / f"_注册表备份_{stamp}"
    bak.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ini_path, bak / "overlays.ini")
    print()
    print(f"  已备份到 {bak.name}/overlays.ini")

    out = "".join(preamble) + "".join("".join(body) for _, body in keepers)
    # 确保文件以换行结尾
    if out and not out.endswith("\n"):
        out += "\n"

    ini_path.write_bytes(out.encode("utf-8"))
    print(f"  已删除 {len(orphans)} 个孤儿段，保留 {len(keepers)} 个有效段")

    # 回读校验
    after = ini_path.read_text(encoding="utf-8")
    _, after_sections = split_sections(after)
    after_names = {n for n, _ in after_sections}
    leftover = [n for n, _ in orphans if n in after_names]
    if leftover:
        print(f"  ★ 回读发现仍有残留: {leftover}")
        return 1
    kept = [n for n, _ in keepers if n not in after_names]
    if kept:
        print(f"  ★ 回读发现有效段丢失: {kept}")
        return 1

    print(f"  [OK] 回读校验通过（{len(after_sections)} 个段，孤儿已清除）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
