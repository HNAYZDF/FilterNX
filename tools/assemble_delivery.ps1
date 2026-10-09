#!/usr/bin/env pwsh
# 组装「超能滤镜」完整交付包到桌面
#
# 一次生成发给群友所需的全部内容:
#   · 安装包（switch 目录，直接合并到 SD 卡根目录）
#   · 安装说明（中文）
#   · 效果图（4 张）
#   · 介绍视频（MP4）
#   · 一键打包 zip
#
# 所有内容都从 filternx/ 的构建产物复制，不手工维护副本 ——
# 避免"桌面上的版本和实际构建不一致"。

$ErrorActionPreference = 'Stop'

# ⚠ 本脚本位于 filternx/tools/ 下，所以 filternx 根目录要往上两层。
#   只上一层的写法会让 $ROOT 变成 filternx\tools，
#   后续所有路径（overlay\src\version.hpp 等）全部找不到。
$ROOT  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DIST  = Join-Path $ROOT 'dist'
$PREV  = Join-Path $ROOT 'preview'
$VIDEO = Join-Path $ROOT 'video'

# 版本号从 version.hpp 读（唯一来源）
$verHpp = Join-Path $ROOT 'overlay\src\version.hpp'
$ver = (Select-String -Path $verHpp -Pattern '^#define\s+FNX_VERSION\s+"([^"]+)"' |
        Select-Object -First 1).Matches[0].Groups[1].Value
if (-not $ver) { throw "无法从 $verHpp 读出版本号" }

Write-Host "=== 组装交付包 v$ver ==="

# ── 清理桌面上的旧交付物 ──
Get-ChildItem 'C:\Users\hnayz\Desktop' |
    Where-Object { $_.Name -like '超能滤镜*' } |
    ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
Write-Host "  已清理桌面旧交付物"

# ── 组装 ──
$desk = "C:\Users\hnayz\Desktop\超能滤镜-v$ver"
New-Item -ItemType Directory -Force -Path $desk | Out-Null

Copy-Item (Join-Path $DIST 'switch') $desk -Recurse -Force
# ⚠ 不要只拷固定几个文件名。文档拆成「安装说明 / 开发说明 / 更新日志」之后，
#   写死清单会让新文档静默漏掉（曾经桌面包里就只有安装说明，没有开发说明）。
#   直接从 dist 拷**全部** .md 与 LICENSE，dist 由 package.sh 生成，是唯一来源。
foreach ($f in (Get-ChildItem $DIST -File -Filter '*.md' -ErrorAction SilentlyContinue)) {
    Copy-Item $f.FullName $desk -Force
}
$lic = Join-Path $DIST 'LICENSE'
if (Test-Path $lic) { Copy-Item $lic $desk -Force }
if (Test-Path $PREV) { Copy-Item $PREV (Join-Path $desk '效果图') -Recurse -Force }

$mp4s = Get-ChildItem $VIDEO -Filter '*.mp4' -ErrorAction SilentlyContinue
$narrated = $mp4s | Where-Object { $_.Name -like '*旁白*' } | Select-Object -First 1
$silent   = $mp4s | Where-Object { $_.Name -notlike '*旁白*' } | Select-Object -First 1
# 两个版本都收 —— 群里很多人静音刷，纯字幕版反而清楚；
# 想听讲解的用旁白版。命名要一眼能分清是哪个。
if ($silent)   { Copy-Item $silent.FullName   (Join-Path $desk '介绍视频-纯字幕.mp4') -Force }
if ($narrated) { Copy-Item $narrated.FullName (Join-Path $desk '介绍视频-中文旁白.mp4') -Force }

# ── 桌面快捷副本（方便直接发）──
if ($narrated) { Copy-Item $narrated.FullName 'C:\Users\hnayz\Desktop\超能滤镜-介绍视频-中文旁白.mp4' -Force }
if ($silent)   { Copy-Item $silent.FullName   'C:\Users\hnayz\Desktop\超能滤镜-介绍视频.mp4' -Force }
$sheet = Join-Path $PREV '00-三页总览.png'
if (Test-Path $sheet) {
    Copy-Item $sheet 'C:\Users\hnayz\Desktop\超能滤镜-效果图.png' -Force
}

# ── zip ──
$zip = Join-Path $ROOT "超能滤镜-v$ver.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $DIST '*') -DestinationPath $zip -Force
Copy-Item $zip "C:\Users\hnayz\Desktop\超能滤镜-v$ver.zip" -Force

# ── 报告 ──
Write-Host ""
Write-Host "=== 桌面交付物 ==="
Get-ChildItem 'C:\Users\hnayz\Desktop' |
    Where-Object { $_.Name -like '超能滤镜*' } |
    ForEach-Object {
        if ($_.PSIsContainer) {
            Write-Host "  [目录] $($_.Name)"
            Get-ChildItem $_.FullName -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Replace($desk, '')
                Write-Host ("           {0,-40} {1,8:N0} KB" -f $rel, ($_.Length / 1KB))
            }
        } else {
            Write-Host ("  {0,-42} {1,8:N0} KB" -f $_.Name, ($_.Length / 1KB))
        }
    }

$ovl = Join-Path $DIST 'switch\.overlays\Chaoneng.ovl'
if (Test-Path $ovl) {
    Write-Host ""
    Write-Host "=== 安装文件校验 ==="
    Write-Host "  Chaoneng.ovl  $((Get-Item $ovl).Length) 字节"
    Write-Host "  SHA256: $((Get-FileHash $ovl -Algorithm SHA256).Hash)"
}
