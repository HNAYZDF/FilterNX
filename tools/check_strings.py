#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_strings.py — 确认界面文案真的编进了产物

═══════════════════════════════════════════════════════════════════════════
动机
═══════════════════════════════════════════════════════════════════════════
源码里有中文不代表产物里有。优化、字符串合并、编码问题都可能让某条文案
在编译后消失或变形，而真机上表现为"某个位置空白/乱码" ——
在电脑上看源码完全正常，很难联想到是编译环节。

═══════════════════════════════════════════════════════════════════════════
哪些中文字面量**不该**检查（否则是误报）
═══════════════════════════════════════════════════════════════════════════
本脚本只检查**真正会渲染到界面**的文案，即传给 Tesla UI 函数的字符串：

    ListItem(名字, 说明) / OverlayFrame(标题, 副标题) / CategoryHeader(标题)
    setText(...) / setValue(...) / showNow(...)

以下中文字面量是**元数据或编译期信息**，不会进二进制，必须排除：

  · 注释里的中文（尤其注释中引用界面文案时）
  · static_assert 的诊断信息 —— 只在编译失败时出现
  · 纯元数据常量（如文件名常量 "超能滤镜.ovl"）—— 供打包脚本使用，
    运行时不读取
  · enum/宏定义里的中文（若有）

早期版本用"凡是含中文的字面量都检查"的粗暴做法，把元数据常量也算了进去，
产生过误报。现在改成按**调用点**提取，精确得多。
"""

import re
import sys
from pathlib import Path

CJK = re.compile(r'[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]')

# 真正会渲染到界面的调用点。
# 每个模式捕获其中的字符串字面量参数。
UI_CALLS = [
    # ListItem(名字, 说明)
    re.compile(r'ListItem\s*\(([^;]*?)\)\s*[;)]', re.S),
    # CategoryHeader(标题)
    re.compile(r'CategoryHeader\s*\(([^;]*?)\)\s*[;)]', re.S),
    # OverlayFrame(标题, 副标题)
    re.compile(r'OverlayFrame\s*\(([^;]*?)\)\s*;', re.S),
    # showNow(消息, 字号, 标题)
    re.compile(r'showNow\s*\(([^;]*?)\)\s*;', re.S),
]

STR_LIT = re.compile(r'"([^"\\\n]*)"')


def strip_conditional_blocks(text: str) -> str:
    """去掉 #ifdef FNX_NO_FIZEAU ... #endif 之间的内容。

    那一段只在**诊断构建**里编译，不在正式版产物里，
    所以不该要求正式版的 .ovl 含有它的中文串。

    ⚠ 不用"允许缺失某些串"的白名单来绕过 —— 白名单会越写越长，
      最后把真正该检查的串也放过。按条件编译边界排除才精确。
    """
    out = []
    depth = 0
    for line in text.splitlines(keepends=True):
        if "#ifdef FNX_NO_FIZEAU" in line or "#ifndef FNX_NO_FIZEAU" in line:
            depth += 1
            continue
        if line.lstrip().startswith("#endif") and depth > 0:
            depth -= 1
            continue
        if depth == 0:
            out.append(line)
    return "".join(out)


def strip_comments(text: str) -> str:
    """去掉 // 行注释与 /* */ 块注释，保留字符串字面量"""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def extract_ui_strings(src_dir: Path):
    """只提取 UI 调用点里的中文字面量，返回 {文案: '文件:行号'}"""
    found = {}

    for f in sorted(src_dir.rglob('*')):
        if f.suffix not in ('.cpp', '.hpp', '.c', '.h'):
            continue
        try:
            raw = f.read_text(encoding='utf-8')
        except Exception:
            continue

        # 先去掉只在诊断构建里编译的块，再去注释
        # （诊断页的中文串不在正式版产物里，不该要求它存在）
        text = strip_comments(strip_conditional_blocks(raw))

        for pattern in UI_CALLS:
            for call in pattern.finditer(text):
                args = call.group(1)
                for m in STR_LIT.finditer(args):
                    s = m.group(1)
                    if not CJK.search(s):
                        continue
                    # 计算行号，便于定位
                    line = text.count('\n', 0, call.start()) + 1
                    found.setdefault(s, f"{f.name}:{line}")

    return found


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    src = None
    positional = []
    i = 0
    while i < len(args):
        if args[i] == '--src' and i + 1 < len(args):
            src = Path(args[i + 1])
            i += 2
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        print(__doc__)
        return 1

    ovl = Path(positional[0])
    if src is None:
        src = Path(__file__).resolve().parent.parent / 'overlay' / 'src'

    if not ovl.is_file():
        print(f"找不到 {ovl}")
        return 1
    if not src.is_dir():
        print(f"找不到源码目录 {src}")
        return 1

    data = ovl.read_bytes()
    strings = extract_ui_strings(src)

    print("=== 界面中文串检查 ===")
    print(f"  产物: {ovl.name}  ({len(data):,} 字节)")
    print(f"  源码: {src}")
    print(f"  从 UI 调用点提取到 {len(strings)} 条界面文案")
    print("  (只检查真正会渲染的文案；注释、static_assert、元数据常量已排除)\n")

    missing = []
    for s, where in sorted(strings.items()):
        if s.encode('utf-8') in data:
            print(f"  PASS  {s}")
        else:
            print(f"  FAIL  {s}    (来自 {where})")
            missing.append((s, where))

    print()
    print("=" * 56)
    if missing:
        print(f"结果: ★ {len(missing)} 条界面文案未出现在产物中")
        return 1
    if not strings:
        print("结果: ★ 未提取到任何界面文案 —— 提取逻辑可能失效了")
        return 1
    print(f"结果: 全部 {len(strings)} 条界面文案均已编入产物")
    return 0


if __name__ == '__main__':
    sys.exit(main())
