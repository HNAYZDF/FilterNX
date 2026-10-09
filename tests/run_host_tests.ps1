# FilterNX — 主机侧测试运行器
#
# MSYS2 编译出的 exe 依赖 msys-2.0.dll，需要把 C:\msys64\usr\bin 加入 PATH
# 才能运行。本脚本负责运行并汇总结果。

$ErrorActionPreference = 'Continue'
$env:PATH = "C:\msys64\usr\bin;$env:PATH"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$build = Join-Path $root 'tests\build'

$results = @()

foreach ($name in @('test_ipc', 'test_color')) {
    $exe = Join-Path $build "$name.exe"
    Write-Host ("=" * 62)
    Write-Host " $name"
    Write-Host ("=" * 62)

    if (-not (Test-Path $exe)) {
        Write-Host "  未找到 $exe（请先运行 tests/build_host_tests.sh）"
        $results += [pscustomobject]@{ Name = $name; Result = 'MISSING' }
        continue
    }

    & $exe
    $code = $LASTEXITCODE
    $results += [pscustomobject]@{
        Name   = $name
        Result = if ($code -eq 0) { 'PASS' } else { "FAIL($code)" }
    }
    Write-Host ""
}

Write-Host ("=" * 62)
Write-Host " 主机侧测试汇总"
Write-Host ("=" * 62)
$results | ForEach-Object { Write-Host ("  {0,-14} {1}" -f $_.Name, $_.Result) }
Write-Host ""

if ($results.Result -contains 'FAIL(1)' -or $results.Result -contains 'MISSING') {
    exit 1
} else {
    Write-Host "全部通过"
    exit 0
}
