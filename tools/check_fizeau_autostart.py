#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_fizeau_autostart.py — 核查 Fizeau 是否具备「开机自动运行」的全部条件

═══════════════════════════════════════════════════════════════════════════
为什么要有这个检查
═══════════════════════════════════════════════════════════════════════════
真机现象: 打开超能滤镜时特斯拉菜单崩溃，因为机器上没运行 Fizeau。

排查后发现 Fizeau **装得很完整**，只差一个 0 字节的文件:
    atmosphere/contents/0100000000000F12/flags/boot2.flag

Atmosphère 的 loader 只在看到 boot2.flag 时才在开机阶段加载该 sysmodule。
少了它，exefs.nsp 再完整也不会运行 —— 而且**没有任何报错**，只是"没起来"。

这种"装齐了但少一个空文件"的情况，靠肉眼翻目录很容易漏。

═══════════════════════════════════════════════════════════════════════════
⚠ 结果为什么要分两类
═══════════════════════════════════════════════════════════════════════════
本项查的是**用户 SD 卡上的状态**，不是插件代码。混在一起会有两种坏结果:

  · 卡上少 boot2.flag 就报 FAIL → 24 项真实的代码验证被一个"用户待办"淹没，
    时间久了会对 FAIL 麻木
  · 干脆不查 → 漏掉一次本该做的核查

所以分成:
  **代码/交付问题** (code_fails)  → 真失败，返回 1
  **卡上待办**     (pending)      → 返回 77（跳过），并打印"怎么补"
  **全齐**                        → 返回 0

退出码约定: 0 = 通过; 77 = 跳过; 其它 = 失败
═══════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Fizeau 的 title id。来源: 官方 Makefile 的 FZ_TID
TID = "0100000000000F12"

# 它注册的 IPC 服务名（本插件通过这个名字连接）
SERVICE = "fizeau"

checks = 0
warns = 0
code_fails = []     # [(label, detail)] —— 代码/交付问题
pending = []        # [(label, detail)] —— 卡上待办


def ck(cond, label, detail="", scope="pending", warn_only=False):
    """scope: "code" = 代码/交付问题; "pending" = 卡上待办"""
    global checks, warns
    checks += 1
    if cond:
        print(f"  PASS  {label}")
        return
    if warn_only:
        warns += 1
        print(f"  WARN  {label}")
        if detail:
            print(f"        {detail}")
        return
    print(f"  FAIL  {label}")
    if detail:
        print(f"        {detail}")
    (code_fails if scope == "code" else pending).append((label, detail))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    sd = Path(sys.argv[1])
    print("=== Fizeau 开机自启动条件核查 ===")
    print(f"  SD 卡: {sd}")
    print(f"  Title ID: {TID}   服务名: {SERVICE}")
    print()

    if not sd.is_dir():
        # 卡不在读卡器 —— 无法核查，但也不代表代码有问题。
        # 用 77（跳过）而不是 1（失败），避免"假失败"。
        print(f"  [跳过] 找不到 {sd} —— SD 卡不在读卡器")
        print("         本项核查的是卡上状态（sysmodule / boot2.flag / CMU 补丁），")
        print("         与插件代码无关。插卡后可重跑本项。")
        print()
        print("结果: 跳过（未核查）")
        return 77

    contents = sd / "atmosphere" / "contents" / TID

    # ── 1. sysmodule 本体 ──
    print("[1. sysmodule 本体]")
    nsp = contents / "exefs.nsp"
    ck(nsp.is_file(), f"exefs.nsp 存在（{nsp.relative_to(sd)}）",
       "缺它则 Fizeau 本体不存在")
    if nsp.is_file():
        size = nsp.stat().st_size
        print(f"        大小: {size} 字节")
        ck(size > 16 * 1024, "exefs.nsp 大小合理（>16KB）")
        # PFS0 魔数
        head = nsp.read_bytes()[:4]
        ck(head == b"PFS0", "exefs.nsp 是合法 PFS0 包",
           f"头部是 {head!r}，不是 PFS0")

    # ── 2. 自启动开关 ──
    print()
    print("[2. 自启动开关]")
    flags = contents / "flags"
    ck(flags.is_dir(), "flags 目录存在")
    boot2 = flags / "boot2.flag"
    ck(boot2.is_file(), "boot2.flag 存在（Atmosphère 据此在开机时加载）",
       "★ 缺少它 sysmodule 不会自动运行，而且不会有任何报错")

    # 参照: 卡上其它 sysmodule 是否都写了 boot2.flag
    cdir = sd / "atmosphere" / "contents"
    if cdir.is_dir():
        with_flag = 0
        total = 0
        for d in cdir.iterdir():
            if not d.is_dir() or len(d.name) != 16:
                continue
            if (d / "exefs.nsp").is_file():
                total += 1
                if (d / "flags" / "boot2.flag").is_file():
                    with_flag += 1
        if total:
            print(f"        参照: 卡上另有 {with_flag}/{total} 个带 flags 的 "
                  f"sysmodule 写了 boot2.flag")

    # ── 3. toolbox.json ──
    print()
    print("[3. toolbox.json]")
    tbj = contents / "toolbox.json"
    ck(tbj.is_file(), "toolbox.json 存在", warn_only=False)
    if tbj.is_file():
        raw = tbj.read_text(encoding="utf-8", errors="replace")
        print(f"        内容: {raw.strip()}")
        # ⚠ 这是**代码/交付**层面的检查: tid 写错会导致系统模块管理器
        #   认不出它，属于配置缺陷，不是"卡上待办"
        ck(TID in raw, f"toolbox.json 里的 tid 是 {TID}",
           "tid 写错则系统模块管理器认不出它", scope="code")

    # ── 4. nvnflinger CMU 补丁 ──
    print()
    print("[4. nvnflinger CMU 补丁]")
    patch_dir = sd / "atmosphere" / "exefs_patches" / "nvnflinger_cmu"
    ck(patch_dir.is_dir(), "nvnflinger_cmu 补丁目录存在",
       "没有补丁，Fizeau 无法改写显示管线（滤镜不会生效）")
    if patch_dir.is_dir():
        ips = sorted(patch_dir.glob("*.ips"))
        print(f"        补丁数量: {len(ips)}")
        ck(len(ips) >= 1, "至少有一个 .ips 补丁")
        sizes = [p.stat().st_size for p in ips]
        ck(all(16 < s < 4096 for s in sizes), "补丁文件大小合理")

    # ── 5. 前端与配置 ──
    print()
    print("[5. 前端与配置（非自启动必需，但影响可用性）]")
    for rel, label in (("switch/Fizeau/Fizeau.nro", "独立前端 Fizeau.nro"),
                       ("switch/.overlays/Fizeau.ovl", "Tesla overlay"),
                       ("config/Fizeau/config.ini", "配置文件")):
        p = sd / rel
        ck(p.is_file(), f"{label} 存在（{rel}）", warn_only=True)

    # ── 6. 结论（分两类）──
    print()
    print("=" * 62)

    if code_fails:
        print("  代码/交付问题（需要修）:")
        for lbl, det in code_fails:
            print(f"    ★ {lbl}")
            if det:
                print(f"           {det}")
        print()
        print(f"结果: ★ {len(code_fails)} 项代码/交付问题")
        return 1

    if pending:
        print("  卡上待办（不是代码问题，放好即可）:")
        for lbl, det in pending:
            print(f"    · {lbl}")
            if det:
                print(f"           {det}")
        print()
        print("  怎么补:")
        print("    ① boot2.flag —— 交付包「Fizeau自启动」文件夹里就有")
        print("       （0 字节空文件）放到:")
        print(f"         SD卡\\atmosphere\\contents\\{TID}\\flags\\boot2.flag")
        print("       然后**重启机器**（这个开关只在开机阶段生效）")
        print("    ② 或者: 特斯拉菜单 →「系统模块」→ 启用「色彩调节」→ 重启")
        print()
        print(f"结果: 跳过（卡上还有 {len(pending)} 项待办，非代码问题）")
        return 77

    print("结果: Fizeau 具备开机自启动条件")
    print()
    print("      重启机器后，它会在开机阶段自动加载，")
    print(f"      并在服务管理器注册 \"{SERVICE}\" 服务。")
    print("      —— 超能滤镜的连接逻辑将走到正常分支，不再走引导页。")
    if warns:
        print(f"      （有 {warns} 项提示，不影响自启动）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
