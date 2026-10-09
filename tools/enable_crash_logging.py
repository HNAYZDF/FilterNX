#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enable_crash_logging.py — 开启 Atmosphère 崩溃日志，供排障使用

═══════════════════════════════════════════════════════════════════════════
为什么要改这个
═══════════════════════════════════════════════════════════════════════════
用户报告: Fizeau 未运行时打开插件，**整个特斯拉菜单消失**，
         但卡上 atmosphere/fatal_errors 与 crash_reports 都不存在 ——
         系统根本没写任何崩溃记录，无法定位。

原因之一: fatal_auto_reboot_interval = u64!0x2710 (=10000ms)
         崩溃后 10 秒自动重启，错误画面一闪而过。

本脚本做两件事:
  1. fatal_auto_reboot_interval -> 0   错误画面留在屏幕上，能看到错误码
  2. [erpt] disable_automatic_report_cleanup = 1   报告不被定期清理
并确保 fatal_errors / crash_reports / erpt_reports 目录存在。

⚠ 用的是**逐行**处理而不是整串替换 —— 这个 ini 是 CRLF 换行，
  整串匹配会因为 \\r 而全部失配（第一版就栽在这里，两处改动都报"未找到"）。

改完必须重启才生效。原文已备份到 system_settings.ini.bak-超能滤镜。
═══════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if len(sys.argv) < 2:
    print("用法: enable_crash_logging.py <SD卡根目录>")
    sys.exit(1)

sd = Path(sys.argv[1])
ini = sd / "atmosphere" / "config" / "system_settings.ini"

if not ini.is_file():
    print(f"找不到 {ini}")
    sys.exit(1)

# ── 备份 ──
bak = ini.with_name(ini.name + ".bak-超能滤镜")
if not bak.is_file():
    bak.write_bytes(ini.read_bytes())
    print(f"  已备份 -> {bak.name}")
else:
    print(f"  备份已存在（不覆盖）-> {bak.name}")

# ── 逐行读取（保留原始换行风格）──
raw = ini.read_bytes()
try:
    text = raw.decode("utf-8")
except UnicodeDecodeError:
    text = raw.decode("utf-8", errors="replace")

newline = "\r\n" if "\r\n" in text else "\n"
lines = text.replace("\r\n", "\n").split("\n")

changed = []

# ── 1. fatal_auto_reboot_interval -> 0 ──
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith(";") or "=" not in stripped:
        continue
    key = stripped.split("=", 1)[0].strip()
    if key == "fatal_auto_reboot_interval":
        old = stripped
        lines[i] = ("  ; 改为 0 = 崩溃后不自动重启，把错误画面留在屏幕上（原来 10 秒后重启，"
                    "看不到错误码；排障完可改回 u64!0x2710）"
                    f"{newline}  fatal_auto_reboot_interval = u64!0x0")
        changed.append(f"fatal_auto_reboot_interval: {old} -> u64!0x0")

# ── 2. 插入 [erpt] 段 ──
has_erpt = any(l.strip().lower() == "[erpt]" for l in lines)
if not has_erpt:
    # 插在 [usb] 之前（若没有 [usb] 就追加到末尾）
    pos = None
    for i, l in enumerate(lines):
        if l.strip().lower() == "[usb]":
            pos = i
            break
    block = ["[erpt]",
             "; 保留错误报告，不让系统定期自动清理 —— 排障用",
             "disable_automatic_report_cleanup = u8!0x1",
             ""]
    if pos is None:
        lines.extend([""] + block)
    else:
        lines[pos:pos] = block
    changed.append("[erpt] disable_automatic_report_cleanup = u8!0x1")
else:
    # 段已存在，确保键存在
    insert_at = None
    for i, l in enumerate(lines):
        if l.strip().lower() == "[erpt]":
            insert_at = i + 1
            break
    if insert_at is not None and not any(
            l.strip().startswith("disable_automatic_report_cleanup") for l in lines):
        lines.insert(insert_at, "disable_automatic_report_cleanup = u8!0x1")
        changed.append("[erpt] disable_automatic_report_cleanup = u8!0x1")

# ── 写回 ──
out = newline.join(lines)
ini.write_bytes(out.encode("utf-8"))
print()
if changed:
    print("  已改动:")
    for c in changed:
        print(f"    · {c}")
else:
    print("  （无需改动，配置已是目标状态）")

# ── 3. 确保目录存在 ──
print()
print("  崩溃报告目录:")
for d in ("fatal_errors", "crash_reports", "erpt_reports"):
    p = sd / "atmosphere" / d
    if not p.is_dir():
        p.mkdir(parents=True, exist_ok=True)
        print(f"    [新建] atmosphere/{d}")
    else:
        print(f"    [已有] atmosphere/{d}")

# ── 4. 回读校验 ──
print()
print("  回读校验:")
check = ini.read_text(encoding="utf-8", errors="replace")
ok = True
if "fatal_auto_reboot_interval = u64!0x0" in check:
    print("    PASS  fatal_auto_reboot_interval = 0")
else:
    print("    FAIL  fatal_auto_reboot_interval 未改为 0")
    ok = False
if "disable_automatic_report_cleanup = u8!0x1" in check:
    print("    PASS  disable_automatic_report_cleanup = 1")
else:
    print("    FAIL  disable_automatic_report_cleanup 未写入")
    ok = False

print()
print("=" * 58)
if ok:
    print("结果: 崩溃日志已开启")
    print()
    print("      ⚠ 必须**重启机器**才生效。")
    print("      重启后复现一次崩溃，然后把下面两个目录里的文件给我:")
    print("        atmosphere/fatal_errors/")
    print("        atmosphere/crash_reports/")
    print("      里面有崩溃的模块名与地址 —— 那才是定位问题的依据。")
else:
    print("结果: ★ 有改动未写入，请检查")
sys.exit(0 if ok else 1)
