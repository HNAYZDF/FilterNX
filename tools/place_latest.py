#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
place_latest.py — 把最新版本放到桌面（**文件夹形式，不压缩**）

═══════════════════════════════════════════════════════════════════════════
用户要求（2026-10-07）
═══════════════════════════════════════════════════════════════════════════
    「以后桌面直接生成一个文件夹方便 不要压缩包 还要解压
      旧版本删除 保留新版本」

所以:
  · 产物是**文件夹** `超能滤镜-v<版本>/`，拷到卡上直接拖，不用解压
  · 放新版本前，**删掉桌面上所有旧的** 超能滤镜* 项
  · 只保留最新那一个文件夹

⚠ 删除范围严格限定为 **名字以「超能滤镜」开头的项**。
  桌面上其它任何东西（快捷方式、游戏文件夹、别人的压缩包…）一律不动。
  删除走**回收站**，误删可恢复。

═══════════════════════════════════════════════════════════════════════════
为什么不再打 zip
═══════════════════════════════════════════════════════════════════════════
用户每次都要先解压才能拿到 .ovl，多一步操作。文件夹直接可用。
（要分享给别人时再自己压缩即可 —— 那是用户的选择，不是交付的必要步骤。）
═══════════════════════════════════════════════════════════════════════════
"""

import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# 只删匹配这个前缀的项
WIPE_PREFIX = "超能滤镜"


def get_version():
    t = (ROOT / "overlay" / "src" / "version.hpp").read_text(encoding="utf-8")
    m = re.search(r'#define\s+FNX_VERSION\s+"([^"]+)"', t)
    if not m:
        raise SystemExit("  读不到版本号")
    return m.group(1)


def desktop_dir():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
            if buf.value and Path(buf.value).is_dir():
                return Path(buf.value)
    except Exception:
        pass
    return Path(os.path.expanduser("~")) / "Desktop"


def send_to_recycle_bin(path: Path):
    """删到回收站（可恢复）。失败则退回永久删除并明确报告。"""
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x40
        FOF_NOCONFIRMATION = 0x10
        FOF_SILENT = 0x4
        FOF_NOERRORUI = 0x400

        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        # pFrom 必须以双 NUL 结尾
        op.pFrom = str(path) + "\0\0"
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc == 0:
            return "recycle"
    except Exception:
        pass

    # 退回永久删除
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return "permanent"


def main():
    version = get_version()
    print(f"  版本: {version}")

    ovl = DIST / "switch" / ".overlays" / "Chaoneng.ovl"
    for p in (ovl, DIST / "安装说明.md", DIST / "LICENSE"):
        if not p.is_file():
            raise SystemExit(f"  缺少 {p} —— 请先运行 package.sh")
    print(f"  产物: {ovl.name}  {ovl.stat().st_size:,} 字节")

    desk = desktop_dir()
    print(f"  桌面: {desk}")

    # ── 1. 删除桌面上所有旧的 超能滤镜* 项（走回收站）──
    print()
    print("  [清理旧版本]")
    removed = []
    if desk.is_dir():
        for item in sorted(desk.iterdir()):
            if not item.name.startswith(WIPE_PREFIX):
                continue
            # 不删本次要生成的那个（先删掉再重建，保证内容干净）
            how = send_to_recycle_bin(item)
            removed.append((item.name, how))
    if removed:
        for name, how in removed:
            tag = "回收站" if how == "recycle" else "永久删除"
            print(f"    已删除({tag}): {name}")
    else:
        print("    （没有旧版本）")

    # ── 2. 生成新文件夹 ──
    target = desk / f"{WIPE_PREFIX}-v{version}"
    if target.exists():
        send_to_recycle_bin(target)
    (target / "switch" / ".overlays").mkdir(parents=True)
    (target / "Fizeau自启动").mkdir(parents=True)

    shutil.copy2(ovl, target / "switch" / ".overlays" / "Chaoneng.ovl")
    shutil.copy2(DIST / "安装说明.md", target / "安装说明.md")
    shutil.copy2(DIST / "LICENSE", target / "LICENSE")

    preview = ROOT / "preview"
    if preview.is_dir():
        shutil.copytree(preview, target / "效果图")

    video = ROOT / "video"
    if video.is_dir():
        for mp4 in video.glob("*.mp4"):
            dst = ("介绍视频-中文旁白.mp4" if "旁白" in mp4.name
                   else "介绍视频-纯字幕.mp4")
            shutil.copy2(mp4, target / dst)

    (target / "Fizeau自启动" / "boot2.flag").write_bytes(b"")
    (target / "Fizeau自启动" / "说明.txt").write_text(
        "把 boot2.flag 放到 SD 卡的：\n"
        "\n"
        "    atmosphere\\contents\\0100000000000F12\\flags\\\n"
        "\n"
        "（flags 文件夹不存在就新建一个）\n"
        "\n"
        "这是 Fizeau（色彩调节）的「开机自动启动」开关。\n"
        "Atmosphere 的加载器只在看到这个文件时，才会在开机阶段\n"
        "加载它的系统模块。少了它，exefs.nsp 装得再完整也不会运行，\n"
        "而且不会有任何报错。\n"
        "\n"
        "文件是空的，0 字节就对了。\n"
        "\n"
        "放好后必须【重启机器】，这个开关只在开机阶段生效。\n"
        "\n"
        "\n"
        "也可以这样做（效果一样）：\n"
        "  特斯拉菜单 →「系统模块」→ 启用「色彩调节」→ 重启机器\n"
        "\n"
        "\n"
        "注意：换包工具可能把这个文件冲掉，重新放一次即可。\n",
        encoding="utf-8")

    # 安装位置提示
    (target / "【怎么装】.txt").write_text(
        "把 switch 文件夹里的东西，合并到 SD 卡根目录：\n"
        "\n"
        "    本文件夹\\switch\\.overlays\\Chaoneng.ovl\n"
        "                    ↓ 复制到\n"
        "    SD卡\\switch\\.overlays\\Chaoneng.ovl\n"
        "\n"
        "\n"
        "装完后重启机器，打开特斯拉菜单就能看到「超能滤镜」。\n"
        "\n"
        "特斯拉菜单的打开方式：\n"
        "    L + 十字键下 + 右摇杆按下\n"
        "\n"
        "\n"
        "如果打开插件显示「未检测到 Fizeau」：\n"
        "    见「Fizeau自启动」文件夹里的说明。\n"
        "    简单说就是：特斯拉菜单 →「系统模块」→ 启用「色彩调节」\n"
        "    → 重启机器。\n",
        encoding="utf-8")

    print()
    print(f"  已生成文件夹: {target.name}")

    # ── 3. 校验 ──
    print()
    print("  校验:")
    ok = True
    placed = target / "switch" / ".overlays" / "Chaoneng.ovl"
    if placed.read_bytes() == ovl.read_bytes():
        print("    PASS  Chaoneng.ovl 与 dist 逐字节一致")
    else:
        print("    ★     Chaoneng.ovl 与 dist 不一致")
        ok = False

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from nacp_layout import find_nacp, get_name, get_version as gv
        blob = placed.read_bytes()
        off, _, _ = find_nacp(blob)
        nm, vr = get_name(blob, off), gv(blob, off)
        print(f"    PASS  NACP 名字 = {nm!r}")
        if vr == version:
            print(f"    PASS  NACP 版本 = {vr!r}")
        else:
            print(f"    ★     NACP 版本 = {vr!r}，与源码 {version!r} 不一致")
            ok = False
        print(f"    大小   = {len(blob):,} 字节")
        print(f"    SHA256 = {hashlib.sha256(blob).hexdigest().upper()}")
    except Exception as e:
        print(f"    （NACP 校验跳过: {e}）")

    # 桌面只剩一项
    print()
    print("  桌面上的超能滤镜项:")
    leftovers = sorted(p.name for p in desk.iterdir()
                       if p.name.startswith(WIPE_PREFIX))
    for n in leftovers:
        print(f"    {n}")
    if len(leftovers) != 1:
        print(f"    ★ 期望只剩 1 项，实际 {len(leftovers)} 项")
        ok = False

    print()
    print("  文件夹内容:")
    for p in sorted(target.rglob("*")):
        rel = p.relative_to(target).as_posix()
        if p.is_dir():
            print(f"    [D] {rel}/")
        else:
            print(f"        {rel:<44} {p.stat().st_size:>10,} 字节")

    print()
    print("=" * 62)
    if not ok:
        print("结果: ★ 有问题")
        return 1
    print(f"结果: 桌面已生成文件夹 超能滤镜-v{version}/（免解压，旧版本已清理）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
