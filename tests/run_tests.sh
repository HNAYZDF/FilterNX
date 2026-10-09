#!/bin/bash
# 运行主机侧测试（在 msys2 环境里，PATH 完整）
set -u
cd "$(dirname "$0")/build" || exit 1

TESTS="verify_nacp_offsets test_fizeau_proto test_presets test_layout"

echo "  运行主机侧测试:"
for t in $TESTS; do
    if [ ! -x "./$t.exe" ]; then
        printf '    %-22s %s\n' "$t" "缺少 exe"
        continue
    fi
    ./"$t".exe > "/tmp/fnx_$t.log" 2>&1
    rc=$?
    p=$(grep -c 'PASS' "/tmp/fnx_$t.log" 2>/dev/null)
    f=$(grep -c 'FAIL' "/tmp/fnx_$t.log" 2>/dev/null)
    printf '    %-22s exit=%-4s PASS=%-4s FAIL=%s\n' "$t" "$rc" "${p:-0}" "${f:-0}"
    if [ "$rc" -ne 0 ]; then
        echo "      --- 输出 ---"
        sed 's/^/      /' "/tmp/fnx_$t.log" | head -20
    fi
done
