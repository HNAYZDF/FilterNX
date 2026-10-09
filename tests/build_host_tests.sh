#!/usr/bin/env bash
# FilterNX — 主机侧测试编译
#
# 说明: MSYS2 的 g++ 生成的 exe 依赖 msys-2.0.dll，本环境运行时找不到，
#       因此这里只负责【编译】，运行交由 run_host_tests.ps1
#       （它会先把 C:\msys64\usr\bin 加入 PATH）。
#
# 测试范围（只测当前真实生效的代码）:
#   test_fizeau_proto — Fizeau IPC 协议布局（结构体尺寸、字段偏移、命令号）
#   test_presets      — 15 个中文预设的数值合法性
#
# 上一版"自带 sysmodule"路线的测试已归档到 _archive/，
# 它们测的代码已不再使用，留着只会误导。
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TESTS="$ROOT/tests"
OUT="$TESTS/build"

mkdir -p "$OUT"

CXXFLAGS="-std=c++23 -O2 -Wall -Wextra -Wno-unused-parameter \
          -DFNX_HOST_TEST -I$ROOT/overlay/src -I$TESTS"

FAILED=0
for t in test_fizeau_proto test_presets test_layout; do
    if [ -f "$TESTS/$t.cpp" ]; then
        printf '编译 %-20s ... ' "$t"
        if g++ $CXXFLAGS -o "$OUT/$t.exe" "$TESTS/$t.cpp" 2>"$OUT/$t.log"; then
            echo "OK"
        else
            echo "失败"
            cat "$OUT/$t.log"
            FAILED=1
        fi
    fi
done

echo
if [ "$FAILED" -eq 0 ]; then
    echo "编译完成: $OUT"
else
    echo "存在编译失败"
    exit 1
fi
