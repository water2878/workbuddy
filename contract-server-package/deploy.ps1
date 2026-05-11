# 畅腾办公系统 - 云端部署脚本 (Windows)
# 使用方法: .\deploy.ps1 -ServerHost "your-server-ip" -ServerUser "root"

param(
    [Parameter(Mandatory=$true)]
    [string]$ServerHost,
    
    [Parameter(Mandatory=$false)]
    [string]$ServerUser = "root",
    
    [Parameter(Mandatory=$false)]
    [string]$RemoteDir = "/opt/contract-server"
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  畅腾办公系统 - 云端部署" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "服务器: ${ServerUser}@${ServerHost}" -ForegroundColor Yellow
Write-Host "远程目录: ${RemoteDir}" -ForegroundColor Yellow
Write-Host ""

# 检查必要文件
Write-Host "[1/5] 检查必要文件..." -ForegroundColor Green
$requiredFiles = @(
    "contract_server.py",
    "customers_api.py",
    "materials_api.py",
    "product_kb.py",
    "requirements.txt"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        $missingFiles += $file
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host "错误: 缺少以下必要文件:" -ForegroundColor Red
    $missingFiles | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "✓ 文件检查通过" -ForegroundColor Green

# 创建远程目录
Write-Host ""
Write-Host "[2/5] 创建远程目录..." -ForegroundColor Green
$createDirsCmd = "mkdir -p ${RemoteDir}/{web,templates,assets/{images,products},data/{contracts,customers}}"
ssh ${ServerUser}@${ServerHost} $createDirsCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 无法创建远程目录，请检查SSH连接" -ForegroundColor Red
    exit 1
}
Write-Host "✓ 远程目录创建完成" -ForegroundColor Green

# 上传Python文件
Write-Host ""
Write-Host "[3/5] 上传后端文件..." -ForegroundColor Green
$pyFiles = Get-ChildItem -Filter "*.py" | Select-Object -ExpandProperty Name
$pyFiles += "requirements.txt"
if (Test-Path ".env") {
    $pyFiles += ".env"
}

foreach ($file in $pyFiles) {
    Write-Host "  上传 $file..."
    scp $file "${ServerUser}@${ServerHost}:${RemoteDir}/"
}
Write-Host "✓ 后端文件上传完成" -ForegroundColor Green

# 上传前端文件
Write-Host ""
Write-Host "[4/5] 上传前端文件..." -ForegroundColor Green
$webFiles = Get-ChildItem -Path "web" -File | Select-Object -ExpandProperty Name
foreach ($file in $webFiles) {
    Write-Host "  上传 web/$file..."
    scp "web/$file" "${ServerUser}@${ServerHost}:${RemoteDir}/web/"
}
Write-Host "✓ 前端文件上传完成" -ForegroundColor Green

# 上传模板
Write-Host ""
Write-Host "[5/5] 上传合同模板..." -ForegroundColor Green
if (Test-Path "templates/*.xlsx") {
    scp "templates/*.xlsx" "${ServerUser}@${ServerHost}:${RemoteDir}/templates/"
    Write-Host "✓ 模板上传完成" -ForegroundColor Green
} else {
    Write-Host "⚠ 模板文件不存在，跳过" -ForegroundColor Yellow
}

# 初始化数据文件
Write-Host ""
Write-Host "[额外] 初始化数据文件..." -ForegroundColor Green
$initCmd = @"
cd ${RemoteDir}

# 创建空的数据文件
if [ ! -f data/customers/pending.json ]; then echo '[]' > data/customers/pending.json; fi
if [ ! -f data/customers/approved.json ]; then echo '[]' > data/customers/approved.json; fi
if [ ! -f data/customers/sent.json ]; then echo '[]' > data/customers/sent.json; fi
if [ ! -f data/contracts/contracts.json ]; then echo '{}' > data/contracts/contracts.json; fi

# 安装依赖
pip3 install -r requirements.txt

echo "✓ 数据文件初始化完成"
"@

ssh ${ServerUser}@${ServerHost} $initCmd

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  部署完成!" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动命令:" -ForegroundColor Yellow
Write-Host "  ssh ${ServerUser}@${ServerHost} 'cd ${RemoteDir} && python3 contract_server.py'" -ForegroundColor White
Write-Host ""
Write-Host "或使用后台运行:" -ForegroundColor Yellow
Write-Host "  ssh ${ServerUser}@${ServerHost} 'cd ${RemoteDir} && nohup python3 contract_server.py > server.log 2>&1 &'" -ForegroundColor White
Write-Host ""
Write-Host "访问地址: http://${ServerHost}:5032" -ForegroundColor Green
Write-Host ""
Write-Host "文件清单:" -ForegroundColor Yellow
Write-Host "  - 后端API: contract_server.py, customers_api.py, materials_api.py, product_kb.py" -ForegroundColor Gray
Write-Host "  - 前端页面: web/*.html, web/*.js" -ForegroundColor Gray
Write-Host "  - 配置文件: requirements.txt, .env" -ForegroundColor Gray
Write-Host "  - 数据目录: data/{contracts,customers}/" -ForegroundColor Gray
Write-Host "  - 静态资源: assets/{images,products}/" -ForegroundColor Gray
Write-Host ""
