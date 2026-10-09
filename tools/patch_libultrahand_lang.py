#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_libultrahand_lang.py — 把 libultrahand 的默认界面文案汉化

═══════════════════════════════════════════════════════════════════════════
问题
═══════════════════════════════════════════════════════════════════════════
特斯拉菜单底部的按键提示显示英文 `Back` / `OK`，而其他中文 overlay
（ovl-sysmodules、ldn_mitm、sys-tune…）显示的是 `返回` / `确定`。

原因在 `libultra/libra/source/tsl_utils.cpp`:

    struct LangEntry { std::string* var; const char* key; const char* defaultVal; };
    static constexpr LangEntry LANG_TABLE[] = {
        {&OK,   "OK",   "OK"},      // ← 英文默认值
        {&BACK, "BACK", "Back"},
        ...
    };

框架启动时调 `parseLanguage(jsonFile)` 从语言文件覆盖这些默认值；
**读不到文件就原样保留英文默认值**（见 `parseLanguage`：

        *var = (it != jsonMap.end()) ? it->second : defaultVal;

我的构建没有语言文件，所以全部显示英文。

═══════════════════════════════════════════════════════════════════════════
修法为什么选"改默认值"而不是"塞一个语言文件"
═══════════════════════════════════════════════════════════════════════════
塞语言文件依赖两个不确定的东西:
  · 文件要放对路径，而路径随 Ultrahand 版本变
  · 用户装其他整合包时可能被覆盖

改默认值是**编译进二进制**的 —— 不依赖任何外部文件，
任何环境下都显示中文。对一个"全中文插件"来说这是正确的取舍。

⚠ 这是对 vendored 库（third_party/libultrahand）的**有意修改**。
  将来更新 libultrahand 时，需要重新应用本脚本。
  脚本是幂等的，重复运行安全。
═══════════════════════════════════════════════════════════════════════════
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 要汉化的条目: key -> 中文
#
# ⚠ 译文取自 Ultrahand **官方** zh-cn.json（用户整合包里的
#   config/ultrahand/lang/zh-cn.json），不是我自创的 ——
#   这样与菜单其它地方的中文完全一致。
#
# 只改**界面上真正会看到**的那些；其余保持英文默认值。
TRANSLATIONS = {
    "ON":                    "开",
    "OFF":                   "关",
    "OK":                    "确定",
    "BACK":                  "返回",
    "HIDE":                  "隐藏",
    "CANCEL":                "取消",
    "UNAVAILABLE_SELECTION": "暂无选项",     # 官方译文（我曾误用「不可用」）
    "SYSTEM_RAM":            "系统内存",
    "FREE":                  "剩余",         # 官方译文（我曾误用「可用」）
}

# 结构: {&VAR, "KEY", "default"},
# 捕获三部分，便于只替换第三个（默认值）
ENTRY_RE = re.compile(
    r'(\{\s*&\w+\s*,\s*"([A-Z0-9_]+)"\s*,\s*)((?:"(?:[^"\\]|\\.)*")|(?:\d+))(\s*\})')


def main():
    root = Path(__file__).resolve().parent.parent
    target = (root / "third_party" / "libultrahand" / "libultra" / "source"
              / "tsl_utils.cpp")

    if not target.is_file():
        print(f"  [FAIL] 找不到 {target}")
        return 1

    text = target.read_text(encoding="utf-8")
    changed = []
    already = []

    def repl(m):
        prefix, key, old_val, suffix = m.groups()
        if key not in TRANSLATIONS:
            return m.group(0)
        new_val = f'"{TRANSLATIONS[key]}"'
        if old_val == new_val:
            already.append(key)
            return m.group(0)
        changed.append((key, old_val, new_val))
        return prefix + new_val + suffix

    new_text = ENTRY_RE.sub(repl, text)

    if changed:
        target.write_text(new_text, encoding="utf-8")
        print(f"  已汉化 {len(changed)} 条:")
        for key, old, new in changed:
            print(f"    {key:24} {old}  ->  {new}")
    else:
        print("  （没有需要改的，可能已经汉化过）")

    if already:
        print(f"  已经是中文的 {len(already)} 条: {', '.join(already)}")

    # 复查: 确认关键条目现在是中文
    check = target.read_text(encoding="utf-8")
    print()
    print("  复查:")
    ok = True
    for key, want in TRANSLATIONS.items():
        m = re.search(rf'\{{\s*&\w+\s*,\s*"{re.escape(key)}"\s*,\s*"([^"]*)"\s*\}}',
                      check)
        got = m.group(1) if m else None
        status = "PASS" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"    {status}  {key:24} = {got!r}")

    print()
    print("=" * 60)
    if not ok:
        print("结果: ★ 有条目未汉化")
        return 1
    print("结果: libultrahand 默认界面文案已汉化（不依赖语言文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
