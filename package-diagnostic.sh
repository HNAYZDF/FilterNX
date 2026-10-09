#!/usr/bin/env bash
# 生成"仅 overlay"诊断包，用于隔离崩溃发生在哪一侧
#
# 目的: 如果只装 overlay（不装 sysmodule），
#   · 界面能打开并显示"服务未运行"  → overlay 没问题，崩溃在 sysmodule
#   · 依然把 Tesla 搞崩             → overlay / libultrahand 构建有问题
set -e

ROOT=/c/Users/hnayz/Documents/deepseek-harness/default-workspace/filternx
OUT=$ROOT/dist-overlay-only

rm -rf "$OUT"
mkdir -p "$OUT/switch/.overlays"

cp "$ROOT/overlay/FilterNX.ovl" "$OUT/switch/.overlays/FilterNX.ovl"

cat > "$OUT/如何判断.txt" <<'EOF'
这是【仅 overlay】诊断包，故意不含 sysmodule。

用法:
  1. 把 switch/.overlays/FilterNX.ovl 复制到 SD 卡同名目录
  2. 确认 SD 卡上【没有】下面这个目录（有就改名备份掉）:
       atmosphere/contents/0100000000000F13/
  3. 重启机器
  4. 游戏中按热键，选「FilterNX 滤镜」

判读:
  A) 界面能打开，显示「服务未运行」引导页
     → overlay 完全正常。崩溃原因在 sysmodule 一侧。

  B) 依然崩溃 / Tesla 打不开
     → 问题在 overlay 或 libultrahand 构建本身。

无论 A 还是 B，都请把下面这些文件发我:
  · SD:/atmosphere/fatal_reports/   里最新的那个文件
  · SD:/atmosphere/crash_reports/   里最新的那个文件
  · SD:/filternx-log.txt（如果存在）
EOF

echo "已生成: $OUT"
find "$OUT" -type f | sed "s|$OUT|dist-overlay-only|" | sort
