#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────
# msys_build.sh — 在 MSYS2 bash 里跑 devkitA64 构建（Windows 侧调用入口）
#
# 为什么需要这个脚本:
#   devkitPro 安装在 C:\msys64\opt\devkitpro，但 Windows 的 PATH 里没有
#   make / aarch64-none-elf-*。用 MSYS2 的 bash 启动，先把工具链路径摆好，
#   再进 overlay/ 执行 make —— Makefile 注释里写明「必须在 overlay/ 下运行」，
#   因为 libultrahand 用的是相对路径 ../third_party/libultrahand
#   （Windows 原生 g++ 无法解析 /c/... 形式的虚拟路径）。
#
# 用法:
#   bash tools/msys_build.sh clean     # 干净重编
#   bash tools/msys_build.sh           # 增量编译
# ───────────────────────────────────────────────────────────────────────────
set -u

export DEVKITPRO=/c/msys64/opt/devkitpro
export DEVKITA64=$DEVKITPRO/devkitA64
export PATH="/usr/bin:$DEVKITPRO/tools/bin:$DEVKITA64/bin:$PATH"

ROOT=/c/Users/hnayz/Documents/deepseek-harness/default-workspace/filternx
cd "$ROOT/overlay" || { echo "无法进入 overlay/"; exit 1; }

echo "### PWD=$(pwd)"
echo "### DEVKITPRO=$DEVKITPRO"
echo "### make      -> $(command -v make)"
echo "### g++       -> $(command -v aarch64-none-elf-g++)"
echo "### nacptool  -> $(command -v nacptool)"
echo "### elf2nro   -> $(command -v elf2nro)"
echo "### 源码版本号: $(sed -n 's/^#define FNX_VERSION "\([^"]*\)".*/\1/p' src/version.hpp | head -1)"
echo

if [ "${1:-}" = "clean" ]; then
    echo "### make clean"
    make clean
    echo
fi

echo "### make -j$(nproc)"
make -j"$(nproc)"
rc=$?
echo
echo "### make exit: $rc"
exit $rc
