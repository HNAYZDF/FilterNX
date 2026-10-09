# ══════════════════════════════════════════════════════════════════════════
#  restore_recent.ps1 — 还原回收站里最近一小时内删除的项目
# ══════════════════════════════════════════════════════════════════════════
#
#  用户要求: 「回收站全部还原最近一小时的东西」「不要瞎删了」
#
#  本脚本**只还原，不删除任何东西**。
#
#  做法:
#    1. 枚举回收站，用「删除日期」列筛出最近一小时的项
#    2. 对每一项调用它自己的「还原」动词（与回收站存储位置无关）
#    3. 复查: 这些项是否已离开回收站
#
#  为什么不用手工移动文件:
#    回收站里的文件名是 $R... / $I... 这种内部名字，
#    原始路径保存在 $I 元数据里。用「还原」动词由系统自己处理，
#    不会把文件放错地方。
# ══════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = 'Continue'

$now = Get-Date
$cut = $now.AddHours(-1)

Write-Host ''
Write-Host ("  当前时间: {0}" -f $now.ToString('yyyy/MM/dd HH:mm:ss'))
Write-Host ("  时间窗口: {0} 之后删除的都还原" -f $cut.ToString('yyyy/MM/dd HH:mm:ss'))
Write-Host ''

$sh = New-Object -ComObject Shell.Application
$rb = $sh.Namespace(10)
if (-not $rb) {
    Write-Host '  ★ 取不到回收站' -ForegroundColor Red
    exit 1
}

# ── 1. 挑出目标项 ──
$targets = @()
foreach ($it in $rb.Items()) {
    $raw = $rb.GetDetailsOf($it, 2)
    # 删除日期里可能混入 Unicode 方向控制字符，先清掉
    $clean = ($raw -replace '[^\d/: ]', '').Trim()
    if (-not $clean) { continue }
    try { $dt = [datetime]::Parse($clean) } catch { continue }
    if ($dt -ge $cut) {
        $targets += [PSCustomObject]@{
            Name     = $it.Name
            Deleted  = $dt
            IsFolder = $it.IsFolder
        }
    }
}

if ($targets.Count -eq 0) {
    Write-Host '  （最近一小时内没有删除项）'
    exit 0
}

Write-Host ("  找到 {0} 项:" -f $targets.Count)
$targets | Sort-Object Deleted | ForEach-Object {
    Write-Host ("    {0} {1,-50} {2}" -f `
        $(if ($_.IsFolder) { '[D]' } else { '[F]' }),
        $_.Name, $_.Deleted.ToString('HH:mm'))
}

# ── 2. 逐项还原 ──
Write-Host ''
Write-Host '  开始还原…'

$done = @()
foreach ($it in $rb.Items()) {
    $match = $targets | Where-Object { $_.Name -eq $it.Name }
    if (-not $match) { continue }

    $restored = $false
    foreach ($verb in $it.Verbs()) {
        # 去掉助记符 & 后比对（中英文都认）
        $vn = $verb.Name -replace '&', ''
        if ($vn -in @('还原', '复原', 'Restore')) {
            try {
                $verb.DoIt()
                $restored = $true
                $done += $it.Name
                Write-Host ("    OK  {0}" -f $it.Name) -ForegroundColor Green
            } catch {
                Write-Host ("    ★   {0}: {1}" -f $it.Name, $_.Exception.Message) `
                    -ForegroundColor Red
            }
            break
        }
    }
    if (-not $restored) {
        Write-Host ("    ★   {0}: 没有找到「还原」动词" -f $it.Name) -ForegroundColor Red
    }
}

# ── 3. 复查 ──
Write-Host ''
Write-Host '  复查（这些名字应该已不在回收站里）:'
$still = @()
foreach ($it in $rb.Items()) {
    if ($done -contains $it.Name) { $still += $it.Name }
}
if ($still.Count -eq 0) {
    Write-Host ("    全部 {0} 项已离开回收站" -f $done.Count) -ForegroundColor Green
} else {
    Write-Host ("    ★ 仍在回收站: {0}" -f ($still -join ', ')) -ForegroundColor Yellow
}

Write-Host ''
Write-Host '  桌面当前内容:'
Get-ChildItem 'C:\Users\hnayz\Desktop' -Force |
    Sort-Object Name |
    ForEach-Object {
        Write-Host ("    {0} {1}" -f `
            $(if ($_.PSIsContainer) { '[D]' } else { '[F]' }), $_.Name)
    }
