#!/usr/bin/env bash
# FilterNX overlay 构建驱动（MSYS2 + devkitPro + libultrahand）
#
# 注意: LIBULTRAHAND 必须是相对于 overlay/ 的相对路径，
#       原因见 overlay/Makefile 中的"坑点记录"。
#
# ⚠ 这里不再硬编码工程路径：工作区已从 C:\...\default-workspace 迁到
#   F:\ai\default-workspace，硬编码会让脚本跑到不存在的旧目录。
#   用脚本自身位置定位，迁移后无需修改。
set -e

export DEVKITPRO="${DEVKITPRO:-/c/msys64/opt/devkitpro}"
export DEVKITA64="$DEVKITPRO/devkitA64"
export PATH="/usr/bin:$DEVKITA64/bin:$DEVKITPRO/tools/bin:$PATH"
export MSYS2_ARG_CONV_EXCL='*'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/overlay"
exec make LIBULTRAHAND=../third_party/libultrahand "$@"
