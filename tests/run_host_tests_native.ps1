#!/usr/bin/env pwsh
# ══════════════════════════════════════════════════════════════════════════
#  run_host_tests.ps1 — 编译并运行主机侧测试
# ══════════════════════════════════════════════════════════════════════════
#
#  ⚠ 为什么不用 MSYS2 的 g++（/usr/bin/g++）
#
#    MSYS2 的 g++ 生成的 exe 依赖 msys-2.0.dll，而该运行时启动时
#    需要创建 \BaseNamedObjects\msys-2.0S5-... 命名对象。
#    在本执行环境里这个创建被拒绝（0xC0000022），表现为:
#        *** fatal error - NtCreateDirectoryObject(...): 0xC0000022
#    于是测试全部 "跑不起来"，看起来像测试失败，其实与环境有关。
#
#  解决办法: 用 ucrt64 的原生 g++（C:\msys64\ucrt64\bin\g++.exe）。
#    它生成原生 PE，只依赖 api-ms-win-crt-*.dll 与 libstdc++-6.dll，
#    而后者在 C:\msys64\ucrt64\bin 里 —— 把它加进 PATH 即可运行。
#
#  另外: **编译与运行必须分开**。曾经编译脚本还在写 exe 时就启动它，
#    导致 0xC0000142（STATUS_DLL_INIT_FAILED）—— 那是竞态，不是代码问题。
# ══════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = 'Continue'

$root = Split-Path -Parent $PSScriptRoot
$tests = Join-Path $root 'tests'
$out = Join-Path $tests 'build'

$ucrt = 'C:\msys64\ucrt64\bin'
$CXX = Join-Path $ucrt 'g++.exe'
$CC = Join-Path $ucrt 'gcc.exe'

if (-not (Test-Path $CXX)) {
    Write-Host "  ★ 找不到 ucrt64 g++: $CXX" -ForegroundColor Red
    exit 1
}

# 运行期需要 ucrt64 的 DLL
$env:PATH = "$ucrt;$env:PATH"

New-Item -ItemType Directory -Force -Path $out | Out-Null

# ── 1. 编译阶段 ──
Write-Host ''
Write-Host '  [1/2] 编译主机侧测试' -ForegroundColor Cyan

$cxxflags = @('-std=c++23', '-O2', '-Wall', '-Wextra',
              '-Wno-unused-parameter', '-DFNX_HOST_TEST',
              "-I$root\overlay\src", "-I$tests")

$targets = @()
foreach ($t in @('test_fizeau_proto', 'test_presets', 'test_layout')) {
    $src = Join-Path $tests "$t.cpp"
    if (-not (Test-Path $src)) { continue }
    $exe = Join-Path $out "$t.exe"
    Remove-Item $exe -Force -ErrorAction SilentlyContinue   # 强制重建
    $log = Join-Path $out "$t.log"
    & $CXX @cxxflags -o $exe $src 2>&1 | Out-File $log -Encoding utf8
    if (Test-Path $exe) {
        Write-Host "        $t ... OK"
        $targets += $t
    } else {
        Write-Host "        $t ... ★ 编译失败" -ForegroundColor Red
        if (Test-Path $log) {
            Get-Content $log | Select-Object -First 8 |
                ForEach-Object { Write-Host "            $_" }
        }
    }
}

# NACP 偏移验证（需要 libnx 头）
#
# ⚠ 虽然文件名是 .c，但必须用 **g++** 编译:
#   tests/libnx_types_shim.h 里 `#include <cstdint>` 是 C++ 头，
#   用 gcc 编会报 "cstdint: No such file or directory"。
#   （旧脚本用 MSYS2 的 g++，所以碰巧没暴露这个问题。）
$nacpSrc = Join-Path $tests 'verify_nacp_offsets.c'
if (Test-Path $nacpSrc) {
    $exe = Join-Path $out 'verify_nacp_offsets.exe'
    Remove-Item $exe -Force -ErrorAction SilentlyContinue
    $log = Join-Path $out 'verify_nacp_offsets.log'
    & $CXX '-std=c++23', '-O2', '-x', 'c++',
          '-IC:\devkitPro\libnx\include', "-I$tests",
          '-o', $exe, $nacpSrc 2>&1 | Out-File $log -Encoding utf8
    if (Test-Path $exe) {
        Write-Host "        verify_nacp_offsets ... OK"
        $targets += 'verify_nacp_offsets'
    } else {
        Write-Host "        verify_nacp_offsets ... ★ 编译失败" -ForegroundColor Red
        if (Test-Path $log) {
            Get-Content $log | Select-Object -First 8 |
                ForEach-Object { Write-Host "            $_" }
        }
    }
}

# ── 2. 运行阶段（与编译分离，避免文件竞态）──
Write-Host ''
Write-Host '  [2/2] 运行主机侧测试' -ForegroundColor Cyan

$totalPass = 0
$totalFail = 0
$badExit = 0

foreach ($t in $targets) {
    $exe = Join-Path $out "$t.exe"
    $o = & $exe 2>&1
    $code = $LASTEXITCODE
    $p = ($o | Select-String -Pattern '\bPASS\b' | Measure-Object).Count
    $f = ($o | Select-String -Pattern '\bFAIL\b' | Measure-Object).Count
    $totalPass += $p
    $totalFail += $f
    if ($code -ne 0) { $badExit++ }

    $color = if ($code -eq 0 -and $f -eq 0) { 'Green' } else { 'Red' }
    Write-Host ("        {0,-22} exit={1,-4} PASS={2,-4} FAIL={3}" -f `
                $t, $code, $p, $f) -ForegroundColor $color
    if ($code -ne 0) {
        $o | Select-Object -Last 6 | ForEach-Object { Write-Host "            $_" }
    }
}

Write-Host ''
Write-Host ("  合计: PASS={0}  FAIL={1}  非零退出={2}" -f `
            $totalPass, $totalFail, $badExit)

if ($totalFail -gt 0 -or $badExit -gt 0) { exit 1 }
exit 0
