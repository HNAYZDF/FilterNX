#!/usr/bin/env bash
# FilterNX — 主机侧测试驱动
#
# 在 PC 上用普通 g++ 编译并运行测试，不需要真机。
# 这些测试覆盖的是"可以在电脑上客观验证"的部分：
#   · IPC 协议的字节级往返一致性
#   · CMU 色彩数学的数值正确性
#
# 用法: bash tests/run_host_tests.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TESTS="$ROOT/tests"
SHARED="$ROOT/shared"
OUT="$TESTS/build"

mkdir -p "$OUT"

CXXFLAGS="-std=c++23 -O2 -Wall -Wextra -Wno-unused-parameter \
          -DFNX_HOST_TEST -I$TESTS -I$SHARED"

echo "============================================================"
echo " FilterNX 主机侧测试"
echo "============================================================"
echo

# ─────────────── 测试 1: IPC 协议往返 ───────────────
echo "### 编译 test_ipc.cpp ###"
g++ $CXXFLAGS -o "$OUT/test_ipc" "$TESTS/test_ipc.cpp"
echo "编译通过"
echo
"$OUT/test_ipc"
IPC_RC=$?
echo

# ─────────────── 测试 2: 色彩数学 ───────────────
if [ -f "$TESTS/test_color.cpp" ]; then
    echo "### 编译 test_color.cpp ###"
    g++ $CXXFLAGS -o "$OUT/test_color" "$TESTS/test_color.cpp"
    echo "编译通过"
    echo
    "$OUT/test_color"
    COLOR_RC=$?
    echo
else
    echo "(跳过 test_color.cpp: 不存在)"
    COLOR_RC=0
fi

echo "============================================================"
if [ "$IPC_RC" -eq 0 ] && [ "$COLOR_RC" -eq 0 ]; then
    echo " 主机侧测试: 全部通过"
    exit 0
else
    echo " 主机侧测试: 存在失败 (ipc=$IPC_RC color=$COLOR_RC)"
    exit 1
fi
