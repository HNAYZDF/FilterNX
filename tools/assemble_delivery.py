#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble_delivery.py — 组装最终交付物到桌面

═══════════════════════════════════════════════════════════════════════════
规则（用户明确要求）
═══════════════════════════════════════════════════════════════════════════
    桌面上**只留最新的一个压缩包**，其余全部删除。

所以要:
  1. 先删掉桌面上所有旧的 超能滤镜* / FilterNX* / Chaoneng* 相关项
     （包括旧版本的 zip、解压出来的文件夹、旧源码包）
  2. 生成新的 超能滤镜-v<版本>.zip
  3. 校验 zip 内容与 NACP 元数据
  4. 打印最终桌面状态

为什么固化成本脚本:
  手工清理容易漏 —— 之前桌面上同时存在过 5 个不同版本的散件
  （v1.0.3 / v1.0.6 / v1.0.7 / v1.0.8 / v1.1.1 + 两个源码包），
  用户分不清该装哪个。唯一可靠的做法是**每次交付前全清**。
═══════════════════════════════════════════════════════════════════════════
"""

import hashlib
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DESKTOP = Path(os.path.expanduser("~")) / "Desktop"

# 桌面上凡匹配这些模式的项都会被删除
WIPE_PATTERNS = ("超能滤镜", "FilterNX", "Chaoneng", "filternx")


def main():
    print("=== 组装交付物到桌面 ===\n")

    # ── 0. 取版本号 ──
    ver_hpp = (ROOT / "overlay" / "src" / "version.hpp").read_text(
        encoding="utf-8")
    m = re.search(r'#define\s+FNX_VERSION\s+"([^"]+)"', ver_hpp)
    if not m:
        print("  [FAIL] 读不到版本号")
        return 1
    version = m.group(1)
    print(f"  版本: {version}")

    # ── 1. 检查产物齐全 ──
    ovl = DIST / "switch" / ".overlays" / "Chaoneng.ovl"
    doc = DIST / "安装说明.md"
    lic = DIST / "LICENSE"
    for p in (ovl, doc, lic):
        if not p.is_file():
            print(f"  [FAIL] 缺少 {p} —— 请先运行 package.sh")
            return 1
    print(f"  产物: {ovl.name}  {ovl.stat().st_size:,} 字节")

    # ── 2. 清空桌面上的旧交付物 ──
    print()
    print("  [清理桌面]")
    removed = []
    if DESKTOP.is_dir():
        for item in DESKTOP.iterdir():
            if any(pat in item.name for pat in WIPE_PATTERNS):
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    removed.append(item.name)
                except Exception as e:
                    print(f"    ★ 删除失败 {item.name}: {e}")
    if removed:
        for n in removed:
            print(f"    已删除: {n}")
    else:
        print("    （没有需要删除的旧项）")

    # ── 3. 准备暂存目录 ──
    stage = Path(os.environ.get("TEMP", "/tmp")) / f"fnx_delivery_{version}"
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "switch" / ".overlays").mkdir(parents=True)
    (stage / "Fizeau自启动").mkdir(parents=True)

    # demo: overlay
    shutil.copy2(ovl, stage / "switch" / ".overlays" / "Chaoneng.ovl")
    shutil.copy2(doc, stage / "安装说明.md")
    shutil.copy2(lic, stage / "LICENSE")

    # 效果图
    preview = ROOT / "preview"
    if preview.is_dir():
        shutil.copytree(preview, stage / "效果图")

    # 视频
    video = ROOT / "video"
    if video.is_dir():
        for mp4 in video.glob("*.mp4"):
            dst = ("介绍视频-中文旁白.mp4" if "旁白" in mp4.name
                   else "介绍视频-纯字幕.mp4")
            shutil.copy2(mp4, stage / dst)

    # Fizeau 自启动辅助
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

    # ── 4. 打包 ──
    zip_path = DESKTOP / f"超能滤镜-v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(stage).as_posix())
    print()
    print(f"  已生成: {zip_path.name}  "
          f"({zip_path.stat().st_size / 1024:,.0f} KB)")

    # ── 5. 校验 zip 内容 ──
    print()
    print("  [校验]")
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        ob = z.read("switch/.overlays/Chaoneng.ovl")
    sha = hashlib.sha256(ob).hexdigest().upper()

    ok = True
    if ob != ovl.read_bytes():
        print("    ★ zip 里的 ovl 与 dist 不一致")
        ok = False
    else:
        print("    PASS  zip 里的 ovl 与 dist 逐字节一致")

    # 用项目自己的 NACP 解析器核对元数据
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from nacp_layout import find_nacp, get_name, get_version
        off, _, _ = find_nacp(ob)
        nm, vr = get_name(ob, off), get_version(ob, off)
        print(f"    PASS  NACP 名字 = {nm!r}")
        print(f"    PASS  NACP 版本 = {vr!r}"
              f"{'' if vr == version else '  ★ 与源码版本不一致!'}")
        if vr != version or nm != "超能滤镜":
            ok = False
    except Exception as e:
        print(f"    （NACP 校验跳过: {e}）")

    print(f"    大小 = {len(ob):,} 字节")
    print(f"    SHA256 = {sha}")

    need = ["switch/.overlays/Chaoneng.ovl", "安装说明.md",
            "Fizeau自启动/boot2.flag"]
    for n in need:
        if n not in names:
            print(f"    ★ 缺少 {n}")
            ok = False

    # ── 6. 打印最终桌面状态 ──
    print()
    print("  [桌面最终状态]")
    leftovers = [i.name for i in DESKTOP.iterdir()
                 if any(pat in i.name for pat in WIPE_PATTERNS)]
    for n in sorted(leftovers):
        print(f"    {n}")
    if len(leftovers) != 1:
        print(f"    ★ 期望只剩 1 项，实际 {len(leftovers)} 项")
        ok = False

    print()
    print("=" * 60)
    if not ok:
        print("结果: ★ 有问题需要处理")
        return 1
    print(f"结果: 桌面只剩 超能滤镜-v{version}.zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
