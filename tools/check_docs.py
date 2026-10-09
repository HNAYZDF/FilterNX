#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_docs.py — 检查文档与代码/产物是否一致（防文档漂移）

═══════════════════════════════════════════════════════════════════════════
为什么需要它
═══════════════════════════════════════════════════════════════════════════
这个项目里"文档说的和实际不一样"已经真实发生过:
  · README 写"19 个预设"，实际已扩到 30 个
  · README 写"140 项断言"，加了测试后数字变了
  · 界面文案硬编码"共19种"，扩充预设后变成错误信息

文档漂移比代码 bug 更阴险: 代码错了会崩，文档错了只会**误导人**，
而且没人会发现。

本脚本把文档里可核对的数字/名称全部与实际产物比对:
  1. 版本号（源码 / README / 分发文件名 / NACP）
  2. 预设数量（源码 / README / 界面文案）
  3. 断言数量（实际跑测试统计 / README）
  4. 作者名与 QQ 群（源码 / README）
  5. 验证项数量（verify_all.ps1 的 Header 数 / README）
  6. 文件名（README 说的文件名 / dist 里实际的文件名）
"""

import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"
README = ROOT / "README.md"

checks = 0
fails = 0


def ck(cond, label, detail=""):
    global checks, fails
    checks += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))
        fails += 1


def read(p):
    return p.read_text(encoding="utf-8")


def main():
    print("=== 文档一致性检查（防漂移）===\n")

    if not README.is_file():
        print("  [skip] 没有 README.md")
        return 0
    doc = read(README)

    # ── 1. 版本号 ──
    #
    # ⚠ 版本号检查有误报风险: README 里还会出现**第三方**的版本号
    #   （libultrahand v2.4.2、nx-ovlloader v2.0.2、Fizeau 等），
    #   它们不该被当成"我们的过时版本号"。
    #
    #   做法: 先把已知的第三方版本号从待检集合里剔除，
    #   而不是放宽正则 —— 放宽会让真正的漂移漏掉。
    print("[版本号]")
    ver = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"', read(SRC / "version.hpp"), re.M)
    ver = ver.group(1) if ver else None
    ck(ver is not None, "能从 version.hpp 读出版本号")

    DEP_VERSIONS = {
        "2.4.2",   # libultrahand
        "2.0.2",   # nx-ovlloader
    }

    if ver:
        print(f"        源码版本: {ver}")
        mentioned = set(re.findall(r'\bv(\d+\.\d+\.\d+)\b', doc))
        mentioned |= set(re.findall(r'版本\s*(\d+\.\d+\.\d+)', doc))
        stale = {m for m in mentioned if m != ver and m not in DEP_VERSIONS}
        if mentioned & DEP_VERSIONS:
            print(f"        （已忽略第三方版本号: {sorted(mentioned & DEP_VERSIONS)}）")
        ck(not stale, f"README 里没有过时的自有版本号（发现: {sorted(stale) or '无'}）",
           f"源码是 {ver}，README 里却出现 {sorted(stale)}")

        # 反向检查: README 至少要提一次当前版本，否则读者不知道是什么版本
        ck(ver in doc or f"v{ver}" in doc,
           f"README 里提到了当前版本 {ver}")

    # ── 2. 预设数量 ──
    print("\n[预设数量]")
    ptext = read(SRC / "presets.hpp")
    arr = re.search(r'std::array<Preset,\s*(\d+)>', ptext)
    declared = int(arr.group(1)) if arr else -1
    i = ptext.find("std::array<Preset,")
    j = ptext.find("}};", i)
    actual = len(re.findall(
        r'\{\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*PresetGroup::\w+', ptext[i:j]))
    print(f"        数组声明: {declared}   实际条目: {actual}")
    ck(declared == actual,
       f"数组大小与实际条目数一致（{declared}）",
       f"声明 {declared} 但实际 {actual} —— 多出的槽位是空指针（曾导致崩溃）")

    # README 里写的滤镜数量
    #
    # ⚠ 先剔除**引用内容**再数 —— README 里有一句是引用旧值作反面教材:
    #     这个项目里真实发生过：README 写"19 个预设"而代码已扩到 30 个
    #   那个 19 是"历史记录"，不是"当前声明"，不该判为漂移。
    #
    #   判据: 中文引号 「」 “” 与英文引号 "" 包起来的内容视为引用。
    #   这样比"放宽数字范围"精确 —— 放宽会把真正的漂移一起放过。
    doc_unquoted = re.sub(r'[「“"][^」”"]*[」”"]', '', doc)

    doc_counts = set()
    for m in re.finditer(r'(\d+)\s*种(?:中文)?滤镜', doc_unquoted):
        doc_counts.add(int(m.group(1)))
    for m in re.finditer(r'(\d+)\s*个中文预设', doc_unquoted):
        doc_counts.add(int(m.group(1)))
    for m in re.finditer(r'共(\d+)种', doc_unquoted):
        doc_counts.add(int(m.group(1)))
    stale_counts = {c for c in doc_counts if c != actual}
    ck(not stale_counts,
       f"README 里的滤镜数量与代码一致（{actual}）",
       f"代码是 {actual}，README 里出现 {sorted(stale_counts)}")

    # 界面文案里的数量
    gui = read(SRC / "gui.cpp")
    hardcoded = re.findall(r'ListItem\([^)]*?"共(\d+)种"', gui)
    ck(not hardcoded,
       "界面没有硬编码的滤镜数量（应为动态计算）",
       f"gui.cpp 里发现硬编码: {hardcoded}")

    # ── 3. 作者名与 QQ 群 ──
    print("\n[作者与联系方式]")
    author = re.search(r'ListItem\("作者"\s*,\s*"([^"]+)"\)', gui)
    author = author.group(1) if author else None
    groups = re.findall(r'ListItem\("\d群"\s*,\s*"(\d+)"\)', gui)
    print(f"        作者: {author}   QQ 群: {groups}")
    ck(bool(author), "能从 gui.cpp 读出作者名")
    if author:
        ck(author in doc, f"README 里有作者名 {author}",
           "README 里的作者名与代码不一致")
    ck(len(groups) == 3, f"QQ 群有 3 个（实际 {len(groups)}）")
    for g in groups:
        ck(g in doc, f"README 里有群号 {g}")

    # ── 4. 验证项数量 ──
    #
    # ⚠ 两个坑，都踩过:
    #
    #  坑 1: 不要静态解析 verify_all.ps1 去数 Note **调用次数** ——
    #        同一个名字在条件分支里会出现多次，数出来偏大。
    #        要数的是**不同的检查名**。
    #
    #  坑 2: dist\验证索引.txt 是**上一轮**套件写下的，
    #        而本检查是在本轮套件里跑的 —— 所以索引永远慢一轮。
    #        只看索引会得到"README 写 11、实际 14"这种过时结论。
    #
    #  做法: 两个依据都取，取**较大值**作为真实项数，
    #        并断言脚本里的检查名集合确实是那个数。
    print("\n[验证套件项数]")
    vf = ROOT / "verify_all.ps1"
    script_names = []
    if vf.is_file():
        vt = read(vf)
        # 只匹配 Note 后紧跟字符串字面量的调用，取**唯一**名字
        script_names = sorted(set(re.findall(r"Note\s+'([^']+)'", vt)))
        print(f"        脚本里的检查名: {len(script_names)} 个")
        for n in script_names:
            print(f"          · {n}")

    index = ROOT / "dist" / "验证索引.txt"
    index_n = None
    if index.is_file():
        itext = read(index)
        m = re.search(r'^验证项数=(\d+)', itext, re.M)
        index_n = int(m.group(1)) if m else None
        failed = re.search(r'^失败项数=(\d+)', itext, re.M)
        failed = int(failed.group(1)) if failed else None
        print(f"        上轮索引: {index_n} 项（失败 {failed}）")

    candidates = [n for n in (len(script_names) or None, index_n) if n]
    n_checks = max(candidates) if candidates else None

    if n_checks is None:
        ck(False, "能确定套件项数", "既没有 verify_all.ps1 也没有验证索引")
    else:
        print(f"        采用项数: {n_checks}")
        # 交叉验证: 脚本名数应与索引一致（索引是运行时真值）
        if index_n is not None and script_names:
            ck(len(script_names) == index_n,
               f"脚本检查名数与上轮索引一致（{index_n}）",
               f"脚本 {len(script_names)} 个，索引 {index_n} —— "
               f"可能索引是旧版本写的，重跑一次套件即可对齐")

        m = re.search(r'([一二三四五六七八九十]+|\d+)\s*项检查', doc)
        if m:
            cn = m.group(1)
            zh = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7,
                  '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12, '十三': 13,
                  '十四': 14, '十五': 15, '十六': 16, '十七': 17, '十五': 15, '十六': 16}
            doc_n = zh.get(cn) or (int(cn) if cn.isdigit() else None)
            ck(doc_n == n_checks,
               f"README 的检查项数与实际一致（{n_checks}）",
               f"README 写 {doc_n}，实际 {n_checks} —— 请更新 README")
        else:
            print("        （README 未声明检查项数，跳过）")

    # ── 5. 分发文件名 ──
    print("\n[分发文件名]")
    pkg = ROOT / "package.sh"
    if pkg.is_file():
        pk = read(pkg)
        stem = re.search(r"FILE_STEM='([^']+)'", pk)
        stem = stem.group(1) if stem else None
        out = re.search(r'OUT_NAME="([^"]+)"', pk)
        expected_name = f"{stem}.ovl" if stem else None
        print(f"        package.sh 产出文件名: {expected_name}")
        if expected_name:
            ck(expected_name in doc or (stem or "") in doc,
               f"README 里提到了分发文件名 {expected_name}")
            # 必须是纯 ASCII（中文文件名大气层识别不了）
            ck(expected_name.isascii(),
               f"分发文件名是纯 ASCII（{expected_name}）",
               "中文文件名大气层完全无法识别 —— 曾因此插件不显示")
            # 实际产物
            dist = ROOT / "dist" / "switch" / ".overlays"
            if dist.is_dir():
                files = [p.name for p in dist.glob("*.ovl")]
                ck(files == [expected_name],
                   f"dist 里的产物文件名正确（{files}）",
                   f"期望 [{expected_name}]，实际 {files}")

    # ── 6. README 声称的断言数 ──
    print("\n[断言数]")
    build = ROOT / "tests" / "build"
    total = 0
    per = {}
    if build.is_dir():
        import os
        env = dict(os.environ)
        # ⚠ 必须用 ucrt64 而不是 msys64:
        #   测试 exe 现在由 ucrt64 的原生 g++ 编译，运行时需要
        #   C:\msys64\ucrt64\bin 下的 libstdc++-6.dll 等。
        #   把 msys64\usr\bin 放进 PATH 反而会让它加载 msys-2.0.dll 而崩。
        env["PATH"] = r"C:\msys64\ucrt64\bin;" + env.get("PATH", "")
        # ⚠ 四个测试都要跑，包括 verify_nacp_offsets
        #   （早期漏了它，于是统计出的断言数比实际少 16）
        for exe in ("test_fizeau_proto", "test_presets", "test_layout",
                    "verify_nacp_offsets"):
            p = build / f"{exe}.exe"
            if not p.is_file():
                print(f"        （缺 {exe}.exe，跳过）")
                continue
            try:
                r = subprocess.run([str(p)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   env=env, timeout=60)
                m = re.search(r'检查项:\s*(\d+)', r.stdout or "")
                if m:
                    per[exe] = int(m.group(1))
                    total += int(m.group(1))
                else:
                    # 有的测试用 PASS 计数而不是"检查项:"
                    n = len(re.findall(r'\bPASS\b', r.stdout or ""))
                    if n:
                        per[exe] = n
                        total += n
            except Exception as e:
                print(f"        ★ 跑 {exe} 失败: {e}")
    for k, v in per.items():
        print(f"        {k:20} {v:3} 项")
    print(f"        {'合计':20} {total:3} 项")
    if total:
        m = re.search(r'(\d+)\s*项断言', doc)
        if m:
            ck(int(m.group(1)) == total,
               f"README 的断言数与实测一致（{total}）",
               f"README 写 {m.group(1)}，实测 {total}")

    print("\n" + "=" * 60)
    print(f"检查项: {checks}   失败: {fails}")
    print("结果: " + ("文档与实现一致" if fails == 0 else "★ 文档已漂移，需更新"))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
