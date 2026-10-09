#!/usr/bin/env bash
# FilterNX 构建驱动（MSYS2 + devkitPro）
set -e
export DEVKITPRO=/opt/devkitpro
export DEVKITA64=$DEVKITPRO/devkitA64
export PATH=$DEVKITA64/bin:$DEVKITPRO/tools/bin:$PATH
export MSYS2_ARG_CONV_EXCL='*'

cd /c/Users/hnayz/Documents/deepseek-harness/default-workspace/filternx/sysmodule
exec make "$@"
