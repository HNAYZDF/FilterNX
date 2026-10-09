#!/usr/bin/env pwsh
# 超能滤镜 — 部署到 SD 卡
#
# ═══════════════════════════════════════════════════════════════════════════
# 名字与版本到底存在哪里（读 Ultrahand 源码得到的确切结论）
# ═══════════════════════════════════════════════════════════════════════════
# Ultrahand-Overlay 的 source/utils.hpp:953 getOverlayInfo() 是这样取的:
#
#     fseek(file, nroHeader.size + assetHeader.nacp.offset, SEEK_SET);
#     fread(&nacp, sizeof(NacpStruct), 1, file);
#     ...
#     const char* nameEnd    = memchr(nacp.lang_data.lang[0].name, '\0', ...);
#     const char* versionEnd = memchr(nacp.display_version, '\0', ...);
#     return { ..., std::string(nacp.lang_data.lang[0].name, nameLen),
#                   std::string(nacp.display_version, versionLen), ... };
#
# 即:
#     名字 → NACP 里 lang[0]（语言槽 0）的 name
#     版本 → NACP 的 display_version
#
# 而 source/main.cpp:6894 还有一层覆盖:
#     assignedName    = !customName.empty()    ? customName    : overlayName;
#     assignedVersion = !customVersion.empty() ? customVersion : overlayVersion;
#     （customName/customVersion 来自 config/ultrahand/overlays.ini）
#
# 所以本脚本三层一起做，无论哪套机制生效都能正确显示:
#     ① 文件名          → 超能滤镜.ovl
#     ② NACP 名字/版本   → 超能滤镜 / 6.0.0（打包时已写入，这里回读校验）
#     ③ overlays.ini     → 显式写 custom_name / custom_version
#
# ═══════════════════════════════════════════════════════════════════════════
# 为什么要有这个脚本（踩过的坑）
# ═══════════════════════════════════════════════════════════════════════════
# 之前 overlay 打包好了、名字也改好了，但**从未真正复制到卡上** ——
# 于是打开菜单看到的还是旧文件、旧名字、旧版本。
# **打包 ≠ 部署。** 卡不在读卡器时本脚本直接失败退出，绝不假装成功。
#
# 用法: pwsh -File deploy.ps1
# ═══════════════════════════════════════════════════════════════════════════

param([string]$MockSd = '')

$ErrorActionPreference = 'Stop'

$ROOT      = Split-Path -Parent $MyInvocation.MyCommand.Path
$DIST_OVL  = Join-Path $ROOT 'dist\switch\.overlays\Chaoneng.ovl'
$NEW_NAME  = 'Chaoneng.ovl'
# 需要清理的旧文件名（历史上用过这些；中文文件名大气层不识别，必须清掉）
$OLD_NAMES = @('FilterNX.ovl', '超能滤镜.ovl')
$DISP_NAME = '超能滤镜'

$PY    = 'C:\Users\hnayz\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$TOOLS = Join-Path $ROOT 'tools'
$READ_NACP = Join-Path $ROOT 'tools\read_nacp.py'

# ── 用 Python + nacp_layout.py 直接读 NACP，不解析文本 ──
#
# 早期版本用正则去匹配 read_nacp.py 的文本输出，区段名一改就失配；
# 而且"应用名称"与"发行商"两个区段格式相同，容易取错行。
# 直接从二进制读，并复用 tools/nacp_layout.py 的唯一定义，最可靠。
$NACP_READER = @'
import json, sys
# 强制 stdout 用 UTF-8，否则在 GBK 代码页下中文会被替换成 ?（读回的名字就废了）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
except Exception:
    pass
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from nacp_layout import find_nacp, get_name, get_version, get_author, get_isbn
b = Path(sys.argv[2]).read_bytes()
off, _, _ = find_nacp(b)
if off is None:
    print(json.dumps({"ok": False}))
    sys.exit(0)
print(json.dumps({
    "ok": True,
    "name": get_name(b, off),
    "version": get_version(b, off),
    "author": get_author(b, off),
    "isbn": get_isbn(b, off),
    "offset": off,
}, ensure_ascii=False))
'@

$NacpScript = Join-Path $env:TEMP 'fnx_nacp_read.py'
# 用 UTF-8(无 BOM) 写脚本，避免 Python 把 BOM 当成语法错误
[System.IO.File]::WriteAllText($NacpScript, $NACP_READER,
    (New-Object System.Text.UTF8Encoding($false)))

function Get-NacpInfo([string]$ovlPath) {
    # ⚠ PowerShell 5.1 默认按控制台代码页解码子进程输出，中文会变乱码，
    #   进而让"名字比对"误判失败。这里显式指定 UTF-8 读取。
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $PY
    $psi.Arguments              = '"' + $NacpScript + '" "' + $TOOLS + '" "' + $ovlPath + '"'
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8

    $proc = [System.Diagnostics.Process]::Start($psi)
    $json = $proc.StandardOutput.ReadToEnd()
    $err  = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if (-not $json.Trim()) {
        Write-Host "  [debug] NACP 读取器无输出。stderr: $err" -ForegroundColor Yellow
        return $null
    }
    try { return $json.Trim() | ConvertFrom-Json } catch { return $null }
}

# ── 0. 确认产物并读出它自带的版本 ──
if (-not (Test-Path $DIST_OVL)) {
    Write-Host "★ 找不到打包产物: $DIST_OVL" -ForegroundColor Red
    Write-Host "  请先运行: bash package.sh" -ForegroundColor Yellow
    exit 1
}
$srcHash = (Get-FileHash $DIST_OVL -Algorithm SHA256).Hash
$srcSize = (Get-Item $DIST_OVL).Length

Write-Host "=== 超能滤镜 部署 ==="
Write-Host "  源文件: $NEW_NAME  ($srcSize 字节)"

$info = Get-NacpInfo $DIST_OVL
if (-not $info.Name -or -not $info.Version) {
    Write-Host "★ 无法从产物读出 NACP 名字/版本" -ForegroundColor Red
    exit 1
}
Write-Host "  产物名字: $($info.Name)   (NACP lang[0])"
Write-Host "  产物版本: $($info.Version)   (NACP display_version)"
Write-Host "  SHA256  : $($srcHash.Substring(0,32))..."
Write-Host ""

# ── 1. 找 SD 卡 ──
#
# 支持 -MockSd <路径> 指向一个模拟卡目录，用于端到端自测部署逻辑
# （不然只能等真卡插上才能发现脚本 bug）。生产路径默认仍只认真实可移动盘。
$sd = $null
if ($MockSd) {
    if (Test-Path (Join-Path $MockSd 'atmosphere')) {
        $sd = (Resolve-Path $MockSd).Path.TrimEnd('\')
        Write-Host "[测试模式] 使用模拟卡: $sd" -ForegroundColor Magenta
    } else {
        Write-Host "★ 模拟卡目录缺少 atmosphere 子目录: $MockSd" -ForegroundColor Red
        exit 1
    }
} else {
    foreach ($dl in (Get-Volume | Where-Object { $_.DriveType -eq 'Removable' -and $_.DriveLetter } |
                     Select-Object -ExpandProperty DriveLetter)) {
        if (Test-Path "${dl}:\atmosphere") { $sd = "${dl}:" }
    }
}

if (-not $sd) {
    Write-Host "★ SD 卡不在读卡器 —— 未部署任何文件。" -ForegroundColor Red
    Write-Host ""
    Write-Host "  插上卡后重新运行本脚本。不要以为已经装好了。" -ForegroundColor Yellow
    exit 1
}
Write-Host "SD 卡: $sd"

$dstDir = "$sd\switch\.overlays"
if (-not (Test-Path $dstDir)) {
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    Write-Host "  已创建 $dstDir"
}

# ── 2. 备份 ──
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bak = "$sd\_超能滤镜_backup_$stamp"
New-Item -ItemType Directory -Force -Path $bak | Out-Null

Write-Host ""
Write-Host "=== 备份 ==="
$n = 0
foreach ($nm in (@($OLD_NAMES) + @($NEW_NAME))) {
    $p = "$dstDir\$nm"
    if (Test-Path $p) { Copy-Item $p "$bak\" -Force; Write-Host "  已备份 $nm"; $n++ }
}
if ($n -eq 0) { Write-Host "  （卡上没有现有版本）" }
Write-Host "  备份目录: $($bak.Replace("$sd\",''))"

# ── 3. 部署（临时文件 → 校验 → 改名）──
Write-Host ""
Write-Host "=== 部署 ==="
$final = "$dstDir\$NEW_NAME"
$tmp   = "$final.new"

Copy-Item $DIST_OVL $tmp -Force
if ((Get-FileHash $tmp -Algorithm SHA256).Hash -ne $srcHash) {
    Remove-Item $tmp -Force
    Write-Host "★ 复制校验失败，已删除临时文件，卡上内容未改动" -ForegroundColor Red
    exit 1
}
Move-Item $tmp $final -Force
Write-Host "  已写入 $NEW_NAME（复制校验通过）"

# ── 4. 删除所有旧文件名 ──
#
# 历史上用过这几个名字，都必须清掉，否则菜单里会出现多个条目，
# 或者（中文名那种）大气层根本不识别、看起来像"没装上"。
Write-Host ""
Write-Host "=== 清理旧版本 ==="
$oldRemaining = @()
foreach ($old in $OLD_NAMES) {
    $p = "$dstDir\$old"
    if (Test-Path $p) {
        Remove-Item $p -Force
        Write-Host "  已删除 $old"
    } else {
        Write-Host "  卡上没有 $old"
    }
}

# ── 5. overlays.ini: 清理旧段 + 显式写 custom_name / custom_version ──
#
# Ultrahand 的 main.cpp:6894 会用 custom_name / custom_version 覆盖 NACP 的值。
# 这里显式写入，保证即使 NACP 那层出意外也能显示正确。
$iniPath = "$sd\config\ultrahand\overlays.ini"
if (Test-Path $iniPath) {
    Copy-Item $iniPath "$bak\overlays.ini" -Force
    $ini = Get-Content $iniPath -Raw

    # 删掉所有旧文件名对应的孤儿段
    foreach ($old in $OLD_NAMES) {
        if ($ini -match "(?m)^\[$([regex]::Escape($old))\]") {
            $ini = [regex]::Replace($ini,
                "(?ms)^\[$([regex]::Escape($old))\]\r?\n.*?(?=^\[|\z)", '')
            Write-Host "  已清理 overlays.ini 里的 [$old] 旧段"
        }
    }

    # 写入/更新新文件名对应段的 custom_name 与 custom_version
    $secRe = "(?ms)^\[$([regex]::Escape($NEW_NAME))\]\r?\n(.*?)(?=^\[|\z)"
    $ver = $info.Version
    if ($ini -match "(?m)^\[$([regex]::Escape($NEW_NAME))\]") {
        $ini = [regex]::Replace($ini, $secRe, {
            param($m)
            $body = $m.Groups[1].Value
            $body = [regex]::Replace($body, '(?m)^custom_name\s*=.*$',    "custom_name=")
            $body = [regex]::Replace($body, '(?m)^custom_version\s*=.*$', "custom_version=")
            if ($body -notmatch '(?m)^custom_name\s*=')    { $body = $body.TrimEnd() + "`ncustom_name=`n" }
            if ($body -notmatch '(?m)^custom_version\s*=') { $body = $body.TrimEnd() + "`ncustom_version=`n" }
            return "[$NEW_NAME]`n" + $body
        })
        Write-Host "  已把 overlays.ini 的 custom_* 清空（让 NACP 成为唯一来源）"
    } else {
        $ini = $ini.TrimEnd() + "`n`n[$NEW_NAME]`ncustom_name=`ncustom_version=`nhide=false`nlaunch_args=`npriority=20`nstar=false`nuse_launch_args=false`n"
        Write-Host "  已在 overlays.ini 追加 [$NEW_NAME] 段"
    }

    Set-Content -Path $iniPath -Value $ini -NoNewline
    Write-Host "  overlays.ini 已写入"
} else {
    Write-Host "  overlays.ini 不存在（Ultrahand 首次扫描时会自建，无需处理）"
}

# ── 6. 最终校验 ──
Write-Host ""
Write-Host "=== 校验 ==="
$finalHash = (Get-FileHash $final -Algorithm SHA256).Hash
Write-Host "  卡上大小: $((Get-Item $final).Length) 字节"
if ($finalHash -ne $srcHash) {
    Write-Host "★ 哈希不一致！" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] SHA256 与源文件一致" -ForegroundColor Green

foreach ($old in $OLD_NAMES) {
    if (Test-Path "$dstDir\$old") { $oldRemaining += $old }
}
if ($oldRemaining.Count -gt 0) {
    Write-Host "★ 旧文件仍然存在: $($oldRemaining -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] 旧文件已全部清除" -ForegroundColor Green

$card = Get-NacpInfo $final
Write-Host "  卡上 NACP 名字: $($card.Name)"
Write-Host "  卡上 NACP 版本: $($card.Version)"

Write-Host ""
Write-Host "=== 部署完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "  Ultrahand 列表应显示:  $($card.Name)    $($card.Version)"
Write-Host "  进入插件后标题栏显示:  超能滤镜  v$($card.Version) · 按下即生效"
Write-Host ""
Write-Host "  插件走 IPC，不需要重启。打开 Ultrahand 菜单即可查看。" -ForegroundColor Cyan
Write-Host ""
