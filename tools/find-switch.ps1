# 全面扫描网络，寻找 Switch 的 FTP/日志服务
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "=== 本机网卡 ==="
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.254' } |
    Select-Object IPAddress, InterfaceAlias, PrefixLength | Format-Table -AutoSize

$myIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -match '^192\.168\.' } |
    Select-Object -First 1).IPAddress
if (-not $myIp) { $myIp = '192.168.31.68' }
$base = ($myIp -split '\.')[0..2] -join '.'
Write-Host "扫描网段: $base.0/24`n"

# 端口: sys-ftpd 默认 5000, 也常见 21 / 2121
$ports = @(5000, 21, 2121, 1337)

Write-Host "=== 先看 ARP 表里已有的邻居 ==="
Get-NetNeighbor -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -like "$base.*" -and $_.State -ne 'Unreachable' } |
    Select-Object IPAddress, State, LinkLayerAddress | Format-Table -AutoSize

Write-Host "=== 逐 IP 探测端口 ==="
$found = @()
foreach ($i in 1..254) {
    $ip = "$base.$i"
    if ($ip -eq $myIp) { continue }
    foreach ($port in $ports) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $task = $client.ConnectAsync($ip, $port)
            if ($task.Wait(150) -and $client.Connected) {
                Write-Host ("  FOUND  {0,-16} :{1}" -f $ip, $port) -ForegroundColor Green
                $found += [pscustomobject]@{ IP = $ip; Port = $port }
            }
        } catch { }
        finally { $client.Close() }
    }
}

if ($found.Count -eq 0) {
    Write-Host "  未发现任何开放的 FTP 端口" -ForegroundColor Yellow
    Write-Host "  => Switch 可能没开机 / 没连同一网络 / 没开 sys-ftpd"
} else {
    Write-Host "`n=== 尝试匿名登录 ==="
    foreach ($f in $found) {
        try {
            $req = [System.Net.FtpWebRequest]::Create("ftp://$($f.IP):$($f.Port)/")
            $req.Method = [System.Net.WebRequestMethods+Ftp]::ListDirectory
            $req.Credentials = New-Object System.Net.NetworkCredential("anonymous", "anonymous")
            $req.Timeout = 4000
            $resp = $req.GetResponse()
            $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
            Write-Host "  $($f.IP):$($f.Port) 登录成功，根目录:" -ForegroundColor Green
            $sr.ReadToEnd() -split "`n" | Select-Object -First 25 | ForEach-Object { "    $_" }
            $sr.Close(); $resp.Close()
        } catch {
            Write-Host "  $($f.IP):$($f.Port) 登录失败: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}
