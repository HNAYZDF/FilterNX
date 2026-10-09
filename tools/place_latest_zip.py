#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
place_latest_zip.py — 把最新压缩包放到桌面

═══════════════════════════════════════════════════════════════════════════
⚠ 本脚本**只放，不删**。
  早期版本会在放置前清空桌面上的同类项 —— 那是危险设计，已废弃。
  同名文件存在时直接覆盖（那本来就是同一个交付物），不动其它任何文件。
═══════════════════════════════════════════════════════════════════════════

为什么用 Python 而不是 PowerShell 的 CreateFromDirectory:
    后者生成的 zip 条目用**反斜杠**分隔（`switch\\.overlays\\Chaoneng.ovl`），
    这不符合 zip 规范（APPNOTE 4.4.17 要求正斜杠）。
    Windows 自带解压能忍，但第三方工具（7-Zip、Bandizip、手机端）可能出错。
    Python 的 zipfile 用正斜杠，且能控制压缩级别。
"""

import hashlib
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def get_version():
    t = (ROOT / "overlay" / "src" / "version.hpp").read_text(encoding="utf-8")
    m = re.search(r'#define\s+FNX_VERSION\s+"([^"]+)"', t)
    if not m:
        raise SystemExit("  读不到版本号")
    return m.group(1)


def desktop_dir():
    # 优先问系统（处理 OneDrive 重定向等情况）
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_DESKTOPDIRECTORY = 0x0010
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
            if buf.value and Path(buf.value).is_dir():
                return Path(buf.value)
    except Exception:
        pass
    return Path(os.path.expanduser("~")) / "Desktop"


def main():
    version = get_version()
    print(f"  版本: {version}")

    ovl = DIST / "switch" / ".overlays" / "Chaoneng.ovl"
    for p in (ovl, DIST / "安装说明.md", DIST / "LICENSE"):
        if not p.is_file():
            raise SystemExit(f"  缺少 {p} —— 请先运行 package.sh")
    print(f"  产物: {ovl.name}  {ovl.stat().st_size:,} 字节")

    # ── 组装暂存目录 ──
    stage = Path(tempfile.gettempdir()) / "fnx_zip_stage"
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "switch" / ".overlays").mkdir(parents=True)
    (stage / "Fizeau自启动").mkdir(parents=True)

    shutil.copy2(ovl, stage / "switch" / ".overlays" / "Chaoneng.ovl")
    shutil.copy2(DIST / "安装说明.md", stage / "安装说明.md")
    shutil.copy2(DIST / "LICENSE", stage / "LICENSE")

    preview = ROOT / "preview"
    if preview.is_dir():
        shutil.copytree(preview, stage / "效果图")

    video = ROOT / "video"
    if video.is_dir():
        for mp4 in video.glob("*.mp4"):
            dst = ("介绍视频-中文旁白.mp4" if "旁白" in mp4.name
                   else "介绍视频-纯字幕.mp4")
            shutil.copy2(mp4, stage / dst)

    (stage / "Fizeau自启动" / "boot2.flag").write_bytes(b"")
    (stage / "Fizeau自启动" / "说明.txt").write_text(
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

    # ── 打包到桌面（只放，不删别的）──
    desk = desktop_dir()
    zip_path = desk / f"超能滤镜-v{version}.zip"
    existed = zip_path.exists()

    if existed:
        zip_path.unlink()          # 覆盖同名交付物

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                # 显式用正斜杠（zip 规范要求）
                z.write(p, p.relative_to(stage).as_posix())

    print()
    print(f"  已放置: {zip_path.name}  "
          f"({zip_path.stat().st_size / 1024:,.0f} KB)"
          f"{'  [覆盖了同名旧包]' if existed else '  [新建]'}")

    # ── 校验 ──
    print()
    print("  校验:")
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        key = "switch/.overlays/Chaoneng.ovl"
        if key not in names:
            print(f"    ★ zip 里没有 {key}")
            return 1
        blob = z.read(key)

    ok = True
    # 1. 与 dist 逐字节一致
    if blob == ovl.read_bytes():
        print("    PASS  zip 内 ovl 与 dist 逐字节一致")
    else:
        print("    ★     zip 内 ovl 与 dist 不一致")
        ok = False

    # 2. 路径分隔符
    bad = [n for n in names if "\\" in n]
    if bad:
        print(f"    ★     有条目用了反斜杠: {bad[:3]}")
        ok = False
    else:
        print("    PASS  所有条目用正斜杠（符合 zip 规范）")

    # 3. NACP 元数据
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from nacp_layout import find_nacp, get_name, get_version as gv
        off, _, _ = find_nacp(blob)
        nm, vr = get_name(blob, off), gv(blob, off)
        print(f"    PASS  NACP 名字 = {nm!r}")
        if vr == version:
            print(f"    PASS  NACP 版本 = {vr!r}")
        else:
            print(f"    ★     NACP 版本 = {vr!r}，与源码 {version!r} 不一致")
            ok = False
    except Exception as e:
        print(f"    （NACP 校验跳过: {e}）")

    # 4. 关键文件齐全
    for need in ("switch/.overlays/Chaoneng.ovl", "安装说明.md",
                 "Fizeau自启动/boot2.flag"):
        if need not in names:
            print(f"    ★     缺少 {need}")
            ok = False

    print(f"    大小   = {len(blob):,} 字节")
    print(f"    SHA256 = {hashlib.sha256(blob).hexdigest().upper()}")

    print()
    print("  包内容:")
    with zipfile.ZipFile(zip_path) as z:
        for i in sorted(z.infolist(), key=lambda x: x.filename):
            print(f"    {i.filename:<44} {i.file_size:>10,} 字节")

    print()
    print("=" * 62)
    if not ok:
        print("结果: ★ 有问题")
        return 1
    print(f"结果: 桌面已放置 超能滤镜-v{version}.zip（未删除任何其它文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
