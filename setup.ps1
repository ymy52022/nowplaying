# setup.ps1 —— 建虚拟环境、装依赖、自检。
# 由「安装.bat」调用，也可以自己用 powershell 跑。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Find-Python {
    # 1) 已经建好的 .venv
    $v = Join-Path $root '.venv\Scripts\python.exe'
    if (Test-Path $v) { return $v }

    # 2) py launcher
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch { }
    }

    # 3) PATH 里的 python —— 必须跳过微软商店那个假货
    #    C:\Users\...\AppData\Local\Microsoft\WindowsApps\python.exe
    #    它运行只会弹商店，不是真 Python。
    foreach ($c in (Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($c.Source -notlike '*\WindowsApps\*' -and (Test-Path $c.Source)) { return $c.Source }
    }

    # 4) 常见安装位置
    $cands = @(
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python314\python.exe",
        "C:\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    foreach ($c in $cands) { if (Test-Path $c) { return $c } }
    return $null
}

Write-Host "========================================" 
Write-Host "  nowplaying 安装"
Write-Host "========================================" 
Write-Host ""

Write-Host "[1/4] 找 Python ..."
$py = Find-Python
if (-not $py) {
    Write-Host ""
    Write-Host "[!] 没找到真正的 Python 3.10+" -ForegroundColor Red
    Write-Host ""
    Write-Host "    常见原因：PATH 里只有 Windows 商店那个假的 python.exe。"
    Write-Host "    去「设置 - 应用 - 应用执行别名」把 python.exe / python3.exe 关掉，"
    Write-Host "    再装一次 Python 并勾上 Add python.exe to PATH。"
    Write-Host ""
    Write-Host "    下载：https://www.python.org/downloads/"
    Read-Host "按回车退出"
    exit 1
}
Write-Host "      用：$py"

if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
    Write-Host "[2/4] 创建虚拟环境 .venv ..."
    & $py -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] 创建 venv 失败" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }
} else {
    Write-Host "[2/4] 虚拟环境已存在，跳过"
}

$vpy = Join-Path $root '.venv\Scripts\python.exe'
Write-Host "[3/4] 安装依赖（第一次要几分钟）..."
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[!] 依赖没装成，把上面的报错发出来看看" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host "[4/4] 自检：列一下能听哪些输出设备"
& $vpy (Join-Path $root 'listen.py') --list
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[!] 列设备失败，看看上面报了什么" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host ""
Write-Host "装好了。放首歌，双击「启动.bat」。" -ForegroundColor Green
Read-Host "按回车退出"
