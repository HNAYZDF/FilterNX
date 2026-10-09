# FilterNX — 完整验证套件
#
# 一次跑完全部可在电脑上客观验证的检查。
# 只验证当前真实生效的代码（上一版"自带 sysmodule"路线已归档到 _archive/，
# 那些测试留着只会误导）。
#
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File filternx/verify_all.ps1
#
# ⚠ 本文件必须保存为 **UTF-8 带 BOM**。
#   PowerShell 5.1 会把无 BOM 的文件按系统 ANSI 代码页读取，
#   于是中文全部乱码、进而导致语法解析失败 —— 这个坑踩过不止一次。
#   若用脚本改写本文件，务必用 UTF8Encoding($true)。

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = "C:\msys64\usr\bin;$env:PATH"

$PY   = 'C:\Users\hnayz\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$BASH = 'C:\msys64\usr\bin\bash.exe'
$rootU = $root -replace '\\', '/'
$src = Join-Path $root 'overlay\src'

$results = New-Object System.Collections.ArrayList

function Note($name, $code) {
    # 0 = 通过; 77 = 跳过（外部条件不具备，未核查）; 其它 = 失败
    #   「跳过」必须与「通过」区分开，否则会漏掉本该做的核查。
    #   也必须与「失败」区分开，否则卡没插就会报假失败。
    $r = if ($code -eq 0) { 'PASS' }
         elseif ($code -eq 77) { 'SKIP' }
         else { "FAIL($code)" }
    [void]$results.Add([pscustomobject]@{ Name = $name; Result = $r })
}
function Header($t) {
    Write-Host ''
    Write-Host ('#' * 64)
    Write-Host "# $t"
    Write-Host ('#' * 64)
}

Write-Host ('#' * 64)
Write-Host '# FilterNX 完整验证套件'
Write-Host ('#' * 64)

# ══════════════════════════════════════════════════════════════════
# 0a. 先构建 overlay 本体
# ══════════════════════════════════════════════════════════════════
#
# ⚠ 这一步不能省。曾经出现过一个危险的假通过:
#   源码编译失败，但验证脚本比对的是**上一次构建留下的旧 .ovl**，
#   于是所有检查都"通过"了 —— 而产物其实是陈旧的。
#   所以这里先构建，构建失败就直接终止，绝不拿旧产物继续验证。
Header '0a   构建 overlay'
& $BASH -lc "bash '$rootU/build-overlay.sh' -j4"
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '★ overlay 构建失败 —— 后续检查会比对陈旧产物，因此终止' -ForegroundColor Red
    exit 1
}
$ovlPath = Join-Path $root 'overlay\FilterNX.ovl'
if (-not (Test-Path $ovlPath)) {
    Write-Host "★ 构建后仍找不到 $ovlPath" -ForegroundColor Red
    exit 1
}
$ovlAge = (Get-Date) - (Get-Item $ovlPath).LastWriteTime
if ($ovlAge.TotalMinutes -gt 5) {
    Write-Host "★ 注意: 产物是 $([int]$ovlAge.TotalMinutes) 分钟前构建的，可能不是本次源码" -ForegroundColor Yellow
}
Write-Host "overlay 构建成功: $((Get-Item $ovlPath).Length) 字节"
Note 'overlay 构建' 0

# ══════════════════════════════════════════════════════════════════
# 0b. 编译主机侧测试
# ══════════════════════════════════════════════════════════════════
#
# 编译与运行必须分两步！
# 早先把 "编译 | Out-Null" 和 "运行" 写在相邻两行，出现过
# 0xC0000142 (STATUS_DLL_INIT_FAILED) —— g++ 正在重写 exe 文件的瞬间
# 去执行它就会失败。那是竞态，不是测试本身的问题。
#
# ⚠ 必须用 ucrt64 的原生 g++，不能用 MSYS2 的 /usr/bin/g++:
#   MSYS2 版生成的 exe 依赖 msys-2.0.dll，它启动时要创建
#   \BaseNamedObjects\msys-2.0S5-... ，在本环境被拒（0xC0000022），
#   于是**所有测试都"跑不起来"**，看起来像测试失败，其实与环境有关。
#   run_host_tests_native.ps1 里已处理这一切（含编译/运行分离）。
Header '0b   编译并运行主机侧测试（原生 ucrt64 工具链）'
& powershell -NoProfile -ExecutionPolicy Bypass `
    -File "$root\tests\run_host_tests_native.ps1"
$tests_rc = $LASTEXITCODE
if ($tests_rc -ne 0) {
    Write-Host ''
    Write-Host '★ 主机侧测试未通过' -ForegroundColor Red
    exit 1
}
Write-Host '主机侧测试全部通过'
Note '主机侧测试编译' 0

# ══════════════════════════════════════════════════════════════════
# 1b. NACP 偏移独立验证
# ══════════════════════════════════════════════════════════════════
#
# 用 libnx 官方 nacp.h 让编译器算出真实偏移，与 tools/nacp_layout.py 比对。
#
# 这一项的价值在于**独立**: 不依赖我们自己写的偏移定义。
# 曾经把版本号写进 isbn(0x3000) 而不是 display_version(0x3060)，
# 而回读脚本用了同样错误的偏移 —— 两边错得一致，互相"验证"通过。
# 让编译器按真实 ABI 规则算，才不会有这种共模错误。
#
# 注: 编译已在 run_host_tests_native.ps1 里完成，这里只运行。
Header '1b   NACP 偏移独立验证（依据 libnx 官方 nacp.h）'
$nacpExe = "$root\tests\build\verify_nacp_offsets.exe"
if (-not (Test-Path $nacpExe)) {
    Write-Host '  ★ 缺少 verify_nacp_offsets.exe（上一阶段的编译应该产出它）'
    Note 'NACP 偏移独立验证' 1
} else {
    & $nacpExe
    if ($LASTEXITCODE -ne 0) { Note 'NACP 偏移独立验证' 1 } else { Note 'NACP 偏移独立验证' 0 }
}

# ══════════════════════════════════════════════════════════════════
# 1c. IPC 会话守卫（防崩溃回归）
# ══════════════════════════════════════════════════════════════════
#
# 真实故障: 没装 / 没运行 Fizeau 时，打开插件会把**整个特斯拉菜单搞崩**。
# 根因是 IPC 函数拿空句柄发请求。
#
# ⚠ 这类 bug **只能靠静态检查守住**: 它在"没有 Fizeau 的机器"上才复现。
#   开发机上装了 Fizeau，跑一百次都不会崩 —— 所以"我测试过了"没有意义。
Header '1c   IPC 会话守卫（每个 IPC 函数是否都检查会话）'
& $PY "$root\tools\check_ipc_guards.py"
Note 'IPC 会话守卫' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 1c1. 构建新鲜度（防陈旧 .o 污染产物）
# ══════════════════════════════════════════════════════════════════
#
# 真实事故: 做了一次"临时改服务名 → 构建 → 还原"的验证，
# 还原后 make 没重新编译（.o 比 .hpp 新），产物里一直是测试串。
Header '1c1  构建新鲜度（产物必须比全部源码新）'
& $PY "$root\tools\check_build_fresh.py"
Note '构建新鲜度' $LASTEXITCODE
# ══════════════════════════════════════════════════════════════════
# 1c2. 会话可达性（防止"防崩"把功能删没）
# ══════════════════════════════════════════════════════════════════
#
# 真实事故: 为了"更安全"把所有自动连接都删了，结果**全工程再没有
# 任何地方建立会话** —— 即使 Fizeau 正常开着，插件也永远只显示引导页。
# （这就是「开启后台也不能调用」的原因。）
#
# 教训: 光检查"危险调用被删掉"不够，还要检查**必需调用没被误删**。
Header '1c2  会话可达性（必须有路径能建立 Fizeau 会话）'
& $PY "$root\tools\check_connect_reachable.py"
Note '会话可达性' $LASTEXITCODE
# ══════════════════════════════════════════════════════════════════
# 1d. 「Fizeau 未运行」路径安全性
# ══════════════════════════════════════════════════════════════════
#
# 真机故障: Fizeau 未运行时打开插件 → 整个特斯拉菜单消失。
# 在定位到确切原因之前，本版改用**结构性隔离**而不是继续打补丁:
#   · 初始化阶段零 IPC
#   · 连接前先检查可用性，不可用直接返回
#   · 未连接时 update() 直接返回（不轮询、不重建页面）
#
# 本项用控制流顺序核对以上三条，而不是靠"我记得改过"。
Header '1d   「Fizeau 未运行」路径安全性（初始化零IPC / 检查顺序 / 未连接不重建）'
& $PY "$root\tools\check_fizeau_safety.py"
Note '未连接路径安全' $LASTEXITCODE
# ══════════════════════════════════════════════════════════════════
# 1. Fizeau IPC 协议布局
# ══════════════════════════════════════════════════════════════════
# 运行期需要 ucrt64 的运行时 DLL（libstdc++-6.dll 等）。
# 不加入 PATH 的话退出码是 0xC0000135（找不到 DLL）。
$env:PATH = 'C:\msys64\ucrt64\bin;' + $env:PATH
Header '1    Fizeau IPC 协议布局（结构体尺寸 / 字段偏移 / 命令号）'
& "$root\tests\build\test_fizeau_proto.exe"
Note 'Fizeau IPC 协议布局' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 2. 预设表
# ══════════════════════════════════════════════════════════════════
Header '2    预设表（30 个中文预设的数值合法性 / 区分度 / 分级）'
& "$root\tests\build\test_presets.exe"
Note '预设表数值合法性' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 3. 界面布局约束
# ══════════════════════════════════════════════════════════════════
Header '3    界面布局约束（文字宽度 + 每页高度预算 + 实时刷新）'
& "$root\tests\build\test_layout.exe"
Note '界面布局约束' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 4. NRO 头校验
# ══════════════════════════════════════════════════════════════════
Header '4    NRO 头校验（nx-ovlloader 的加载条件）'
& $PY "$root\tools\check_nro.py" "$root\overlay\FilterNX.ovl"
Note 'NRO 头校验' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 4a. TLS ABI 检查
# ══════════════════════════════════════════════════════════════════
#
# FW 21.0.0 / Atmosphère 1.10.0 改了用户 TLS 的基址（+0x108 → +0x180）。
# 用 libnx < 4.10.0 编出来的 homebrew，其 TLS 会被内核的 thread_cpu_time
# 覆盖，表现为"特定条件下才崩"——正是最难查的那类故障。
#
# 签名与新旧字节对照移植自 hbpatcher（alula 逆向）/ nrodoc。
Header '4a   TLS ABI 检查（产物是否含 FW 21.0.0+ 会破坏的旧签名）'
& $PY "$root\tools\check_tls_abi.py" "$root\overlay\FilterNX.ovl"
Note 'TLS ABI' $LASTEXITCODE
# ══════════════════════════════════════════════════════════════════
# 4b. dist 与当前构建一致性
# ══════════════════════════════════════════════════════════════════
#
# ⚠ 不能直接比 SHA256: overlay/FilterNX.ovl 是**裸产物**，
#   dist/Chaoneng.ovl 是同一份 + package.sh 写入的 NACP 元数据，
#   两者必然不同。比哈希会得出"dist 是旧的"这个**错误结论**
#   —— 我就这么误判过一次，差点去修一个并不存在的问题。
#
#   正确判据: 大小相同 + 所有差异都落在 NACP 元数据字段内 + 元数据 == 源码。
Header '4b   dist 与当前构建一致性（差异是否只在 NACP 元数据）'
& $PY "$root\tools\check_dist_matches_build.py"
Note 'dist 与构建一致' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 5. NRO 结构比对
# ══════════════════════════════════════════════════════════════════
Header '5    NRO 结构比对（与卡上可用 overlay 同构）'
& $PY "$root\tools\compare_nro_struct.py" "$root\overlay\FilterNX.ovl"
Note 'NRO 结构比对' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 6. 界面中文串
# ══════════════════════════════════════════════════════════════════
Header '6    界面中文串已编入产物'
& $PY "$root\tools\check_strings.py" "$root\overlay\FilterNX.ovl"
Note '界面中文串' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 7. 预设表静态检查
# ══════════════════════════════════════════════════════════════════
#
# 独立于 C++ 测试，好处是能精确指出"是哪一个预设有问题"，
# 而 C++ 测试只报通过/失败。
Header '7    预设表静态检查（字段完整性 / 名字前缀混淆）'
Write-Host ''
Write-Host '--- 字段格式 ---'
& $PY "$root\tools\check_preset_table.py"
$rc1 = $LASTEXITCODE
Write-Host ''
Write-Host '--- 名字前缀混淆 ---'
& $PY "$root\tools\check_name_prefix.py"
$rc2 = $LASTEXITCODE
if ($rc1 -ne 0 -or $rc2 -ne 0) { Note '预设表静态检查' 1 } else { Note '预设表静态检查' 0 }

# ══════════════════════════════════════════════════════════════════
# 8. 裁剪检查
# ══════════════════════════════════════════════════════════════════
Header '8    裁剪检查（每页内容是否落在真实裁剪区内）'
& $PY "$root\tools\check_preview_clip.py"
if ($LASTEXITCODE -ne 0) { Note '裁剪检查' 1 } else { Note '裁剪检查' 0 }

# ══════════════════════════════════════════════════════════════════
# 9. 注册表一致性
# ══════════════════════════════════════════════════════════════════
Header '9    注册表一致性（菜单显示值的真正来源）'
Write-Host ''
Write-Host '  自测 check_registry.py（无需硬件）：'
& $PY "$root\tools\test_registry_check.py"
$rcSelf = $LASTEXITCODE
Write-Host ''
# 卡在位时顺便查真实注册表；不在位则明确跳过，不假装通过
$liveSd = $null
$liveChecked = $false
foreach ($dl in (Get-Volume | Where-Object { $_.DriveType -eq 'Removable' -and $_.DriveLetter } |
                 Select-Object -ExpandProperty DriveLetter)) {
    if (Test-Path "${dl}:\atmosphere") { $liveSd = "${dl}:" }
}
if ($liveSd) {
    Write-Host "  实卡注册表检查 ($liveSd):"
    & $PY "$root\tools\check_registry.py" $liveSd
    $rcLive = $LASTEXITCODE
    $liveChecked = $true
} else {
    Write-Host '  [跳过] SD 卡不在读卡器 —— 无法检查实卡注册表'
    Write-Host '         （注意: 跳过不等于通过；插卡后请重跑本项）'
    $rcLive = 0
}
# ⚠ 没插卡时必须记 SKIP(77)，不能记 0(PASS):
#   实卡那一半根本没跑，记成 PASS 会让"25 项全部通过"变成假通过 ——
#   本脚本自己在 Note() 里定义了 77 = 跳过，这里就必须用它。
if ($rcSelf -ne 0 -or $rcLive -ne 0) { Note '注册表一致性' 1 }
elseif (-not $liveChecked) { Note '注册表一致性' 77 }
else { Note '注册表一致性' 0 }

# ══════════════════════════════════════════════════════════════════
# 9b. Fizeau 开机自启动条件
# ══════════════════════════════════════════════════════════════════
#
# 真机故障: 打开插件崩菜单，因为机器上没运行 Fizeau。
# 排查发现 Fizeau 装得很完整，**只差一个 0 字节的 boot2.flag** ——
# Atmosphère 的 loader 只在看到它时才在开机阶段加载该 sysmodule。
#
# 这种"装齐了但少一个空文件"的情况肉眼翻目录极易漏掉，所以逐项核查。
# 需要卡在位；不在位则明确跳过，不假装通过。
Header '9b   Fizeau 开机自启动条件（sysmodule / boot2.flag / 补丁）'
if ($liveSd) {
    & $PY "$root\tools\check_fizeau_autostart.py" $liveSd
    Note 'Fizeau 自启动条件' $LASTEXITCODE
} else {
    Write-Host '  [跳过] SD 卡不在读卡器'
    Write-Host '         （跳过不等于通过 —— 插卡后请重跑本项）'
    # 同上: 记 SKIP 而不是 PASS
    Note 'Fizeau 自启动条件' 77
}

# ══════════════════════════════════════════════════════════════════
# 10. 名字与版本
# ══════════════════════════════════════════════════════════════════
Header '10   名字与版本（NACP 的 lang[0].name 与 display_version）'
& $PY "$root\tools\check_version.py" "$root\dist"
Note '名字与版本' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 11. 文档一致性
# ══════════════════════════════════════════════════════════════════
#
# 防止 README 与实际实现漂移（曾经 README 写"19 个预设"而代码已 30 个）。
# 注意: 本项读的是**上一次**套件导出的验证索引，所以放在最后 ——
# 这样索引里统计的是本轮之前的项数。第一次跑时索引可能不存在，
# 脚本会明确提示而不是假装通过。
Header '11   文档一致性（版本号 / 预设数 / 断言数 / 作者名）'
& $PY "$root\tools\check_docs.py"
Note '文档一致性' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════════════════════════
Write-Host ''
Write-Host ('#' * 64)

# ══════════════════════════════════════════════════════════════════
# 8a2. 框架界面文案汉化
# ══════════════════════════════════════════════════════════════════
#
# 底部按键提示（返回 / 确定 / 隐藏 / 取消）是 libultrahand 画的，不是插件画的。
# 它读语言文件，读不到就用英文默认值 —— 我的构建没有语言文件，
# 所以此前显示 Back / OK。修法是把默认值改成中文（编进二进制）。
Header '8a2  框架界面文案汉化（返回 / 确定 / 隐藏 / 取消）'
& $PY "$root\tools\check_ui_lang.py"
Note '界面文案汉化' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 8a3. 深度审计（未使用代码 / 数值语义 / 实际一致性）
# ══════════════════════════════════════════════════════════════════
#
# 与其它检查器的区别: 那些查**已知的**问题类型，
# 这个查**未知的、跨文件的、语义层的**问题 ——
# 未使用常量/函数、参数集语义重复、数值越界、
# layout 常量与源码实际调用数是否一致。
Header '8a3  深度审计（未使用代码 / 数值语义 / 一致性）'
& $PY "$root\tools\deep_audit.py"
Note '深度审计' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 8b. 端到端链路审计
# ══════════════════════════════════════════════════════════════════
#
# 一次把整条链路的每一环都查一遍，避免"每次只盯一个点改":
#   服务名能否从指令流还原 / IPC 协议 / 连接可达 / 失败安全 /
#   危险调用已清除 / 预设范围 / 元数据一致性
#
# 为什么特别检查"服务名能否从指令流还原":
#   编译器把短字符串内联成 mov/movk 立即数，字节流里**没有连续字符串**。
#   我曾用 `b"fizeau" in bytes` 搜索，搜不到就断定"连接不可能成功"，
#   白白折腾一轮。正确判据是按指令边界还原立即数。
Header '8b   端到端链路审计（打开插件→建立会话→应用滤镜）'
& $PY "$root\tools\audit_full_chain.py"
Note '全链路审计' $LASTEXITCODE

# ══════════════════════════════════════════════════════════════════
# 8c. PowerShell 脚本 BOM
# ══════════════════════════════════════════════════════════════════
#
# PowerShell 5.1 读无 BOM 的 .ps1 会按系统 ANSI 解码。项目脚本含大量中文，
# 一旦缺 BOM: 中文乱码 → 引号/括号错乱 → 脚本被当代码逐行执行。
# 用 edit 工具改 .ps1 会去掉 BOM，所以必须每次检查。
Header '8c   PowerShell 脚本 BOM（UTF-8 with BOM）'
& $PY "$root\tools\check_ps1_bom.py"
Note 'PS脚本BOM' $LASTEXITCODE


Write-Host '# 验证汇总'
Write-Host ('#' * 64)
foreach ($r in $results) { Write-Host ('  {0,-40} {1}' -f $r.Name, $r.Result) }
Write-Host ''

# ── 输出机器可读的验证索引 ──
#
# 为什么要写文件而不是让外部脚本解析本文件:
#   本文件里的 Note 调用有多种写法（有的带字面数字、有的带 $LASTEXITCODE、
#   还有条件分支里同一个名字出现多次）。外部用正则去数**极易数错** ——
#   实际就数错过一次: 静态解析得出"7 项"，真实执行是 13 项，
#   于是 README 的"11 项"既不对着 7 也不对着 13，三方全乱。
#
#   直接由**正在运行的脚本**导出真实结果，是唯一不会漂移的做法。
$indexPath = Join-Path $root 'dist\验证索引.txt'
try {
    $idxDir = Split-Path -Parent $indexPath
    if (-not (Test-Path $idxDir)) { New-Item -ItemType Directory -Force -Path $idxDir | Out-Null }
    $lines = @()
    $lines += '# 由 verify_all.ps1 自动生成，请勿手改'
    $lines += '验证项数=' + $results.Count
    $lines += '通过项数=' + @($results | Where-Object { $_.Result -eq 'PASS' }).Count
    $lines += '失败项数=' + @($results | Where-Object { $_.Result -ne 'PASS' }).Count
    foreach ($r in $results) { $lines += ('项目=' + $r.Name + '|' + $r.Result) }
    # 写 **UTF-8 带 BOM**:
    #   Python 两种都能读，但 PowerShell 5.1 的 Get-Content 默认按 ANSI 读 ——
    #   无 BOM 时中文显示成乱码（文件内容其实是对的，只是查看方式不对）。
    #   带 BOM 让两个工具都读得对，省掉一类"看起来坏了其实没坏"的困惑。
    [System.IO.File]::WriteAllLines($indexPath, $lines, (New-Object System.Text.UTF8Encoding($true)))
    Write-Host "  验证索引已写入: dist\验证索引.txt（$($results.Count) 项）"
} catch {
    Write-Host "  ⚠ 无法写入验证索引: $($_.Exception.Message)"
}
Write-Host ''

$bad  = @($results | Where-Object { $_.Result -ne 'PASS' -and $_.Result -ne 'SKIP' })
$skip = @($results | Where-Object { $_.Result -eq 'SKIP' })
if ($bad.Count -gt 0) {
    Write-Host '存在未通过的检查:' -ForegroundColor Yellow
    foreach ($b in $bad) { Write-Host "  - $($b.Name)  $($b.Result)" }
    exit 1
}
if ($skip.Count -gt 0) {
    Write-Host ''
    Write-Host '跳过的检查（外部条件不具备，未核查 —— 跳过不等于通过）:' -ForegroundColor Yellow
    foreach ($s2 in $skip) { Write-Host "  - $($s2.Name)" }
}
Write-Host '全部验证通过' -ForegroundColor Green
exit 0
