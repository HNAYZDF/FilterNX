#!/usr/bin/env bash
# FilterNX overlay 构建驱动（MSYS2 + devkitPro + libultrahand）
#
# 注意: LIBULTRAHAND 必须是相对于 overlay/ 的相对路径，
#       原因见 overlay/Makefile 中的"坑点记录"。
set -e
export DEVKITPRO=/opt/devkitpro
export DEVKITA64=$DEVKITPRO/devkitA64
export PATH=$DEVKITA64/bin:$DEVKITPRO/tools/bin:$PATH
export MSYS2_ARG_CONV_EXCL='*'

cd /c/Users/hnayz/Documents/deepseek-harness/default-workspace/filternx/overlay
exec make LIBULTRAHAND=../third_party/libultrahand "$@"
