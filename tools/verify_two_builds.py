#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_two_builds.py — 确认正式版与诊断版是**两个不同的**构建

═══════════════════════════════════════════════════════════════════════════
为什么必须验证这个
═══════════════════════════════════════════════════════════════════════════
第一次构建诊断版时，我用错了变量名（CFLAGS_EXTRA，Makefile 里叫 DEFINES），
结果 EXTRA 宏根本没传进去 —— **两份产物字节完全相同**。

如果我直接把那个"诊断版"发给用户，他装上后看到的其实是正式版，
于是"诊断版也崩"这个结论就是**假的**，会把我引向完全错误的排查方向。

所以: 发出去之前必须先证明两个构建真的不同。
"""

import hashlib
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

A = Path(sys.argv[1]) if len(sys.argv) > 1 else None
B = Path(sys.argv[2]) if len(sys.argv) > 2 else None

if not A or not B:
    print("用法: verify_two_builds.py <正式版.ovl> <诊断版.ovl>")
    sys.exit(2)

fails = 0

print("=== 两个构建的差异验证 ===\n")

for label, p in (("正式版", A), ("诊断版", B)):
    if not p.is_file():
        print(f"  ★ 找不到{label}: {p}")
        fails += 1

if fails:
    sys.exit(1)

a = A.read_bytes()
b = B.read_bytes()
ha = hashlib.sha256(a).hexdigest()
hb = hashlib.sha256(b).hexdigest()

print(f"  正式版: {A.name}  {len(a)} 字节")
print(f"          SHA256 {ha}")
print(f"  诊断版: {B.name}  {len(b)} 字节")
print(f"          SHA256 {hb}")
print()

same = ha == hb
if same:
    print("  FAIL  两个构建完全相同 —— 诊断开关没有生效！")
    print("        这样发出去，用户装的其实是正式版，")
    print("        \"诊断版也崩\" 这个结论会是假的。")
    fails += 1
else:
    print("  PASS  两个构建不同（诊断开关已生效）")

# 诊断版应当含"诊断"字样，正式版不应含
diag_marker = "诊断构建".encode("utf-8")
a_has = diag_marker in a
b_has = diag_marker in b
print()
print(f"  PASS  正式版不含「诊断构建」字样" if not a_has else "  FAIL  正式版里出现了「诊断构建」")
if a_has:
    fails += 1
print(f"  PASS  诊断版含「诊断构建」字样" if b_has else "  FAIL  诊断版里没有「诊断构建」")
if not b_has:
    fails += 1

# 差异规模: 只差一个宏的话差异应该很小，但必须是"有小差异"而不是"完全一样"
diff = sum(1 for i in range(min(len(a), len(b))) if a[i] != b[i])
print()
print(f"  差异字节数: {diff}")
if diff == 0:
    print("  FAIL  零差异 —— 开关没生效")
    fails += 1
elif diff > len(a) * 0.5:
    print("  PASS  差异较大（可能是链接布局整体位移，正常）")
else:
    print("  PASS  差异规模合理")

print()
print("=" * 56)
print("结果: " + ("两个构建确实不同，可以用于诊断" if fails == 0
                 else f"★ {fails} 处问题 —— 不要用这两个产物做诊断"))
sys.exit(0 if fails == 0 else 1)
