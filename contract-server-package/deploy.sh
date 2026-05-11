#!/bin/bash
# 畅腾办公系统 - 云端部署脚本
# 使用方法: ./deploy.sh [服务器地址] [服务器用户名]

set -e

# 配置
SERVER_HOST=${1:-"your-server-ip"}
SERVER_USER=${2:-"root"}
REMOTE_DIR="/opt/contract-server"
LOCAL_DIR="."

echo "=========================================="
echo "  畅腾办公系统 - 云端部署"
echo "=========================================="
echo ""
echo "服务器: ${SERVER_USER}@${SERVER_HOST}"
echo "远程目录: ${REMOTE_DIR}"
echo ""

# 检查必要文件
echo "[1/5] 检查必要文件..."
required_files=(
    "contract_server.py"
    "customers_api.py"
    "materials_api.py"
    "product_kb.py"
    "requirements.txt"
)

for file in "${required_files[@]}"; do
    if [ ! -f "${LOCAL_DIR}/${file}" ]; then
        echo "错误: 缺少必要文件 ${file}"
        exit 1
    fi
done
echo "✓ 文件检查通过"

# 创建远程目录
echo ""
echo "[2/5] 创建远程目录..."
ssh ${SERVER_USER}@${SERVER_HOST} "mkdir -p ${REMOTE_DIR}/{web,templates,assets/{images,products},data/{contracts,customers}}"
echo "✓ 远程目录创建完成"

# 上传Python文件
echo ""
echo "[3/5] 上传后端文件..."
scp ${LOCAL_DIR}/*.py ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/requirements.txt ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/.env ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/ 2>/dev/null || echo "警告: .env 文件不存在，跳过"
echo "✓ 后端文件上传完成"

# 上传前端文件
echo ""
echo "[4/5] 上传前端文件..."
scp ${LOCAL_DIR}/web/*.html ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/web/
scp ${LOCAL_DIR}/web/*.js ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/web/
echo "✓ 前端文件上传完成"

# 上传模板
echo ""
echo "[5/5] 上传合同模板..."
scp ${LOCAL_DIR}/templates/*.xlsx ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/templates/ 2>/dev/null || echo "警告: 模板文件上传失败"
echo "✓ 模板上传完成"

# 上传favicon（如果存在）
echo ""
echo "[额外] 上传favicon..."
if [ -f "${LOCAL_DIR}/assets/images/favicon.ico" ]; then
    scp ${LOCAL_DIR}/assets/images/favicon.ico ${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/assets/images/ 2>/dev/null || echo "警告: favicon上传失败"
    echo "✓ favicon上传完成"
else
    echo "⚠ favicon.ico 不存在，跳过上传"
fi

# 初始化数据文件
echo ""
echo "[额外] 初始化数据文件..."
ssh ${SERVER_USER}@${SERVER_HOST} "
    cd ${REMOTE_DIR}
    
    # 创建空的数据文件
    [ ! -f data/customers/pending.json ] && echo '[]' > data/customers/pending.json
    [ ! -f data/customers/approved.json ] && echo '[]' > data/customers/approved.json
    [ ! -f data/customers/sent.json ] && echo '[]' > data/customers/sent.json
    [ ! -f data/contracts/contracts.json ] && echo '{}' > data/contracts/contracts.json
    
    # 安装依赖
    pip3 install -r requirements.txt
    
    echo '✓ 数据文件初始化完成'
"

echo ""
echo "=========================================="
echo "  部署完成!"
echo "=========================================="
echo ""
echo "启动命令:"
echo "  ssh ${SERVER_USER}@${SERVER_HOST} 'cd ${REMOTE_DIR} && python3 contract_server.py'"
echo ""
echo "或使用 systemd 服务:"
echo "  ssh ${SERVER_USER}@${SERVER_HOST} 'systemctl start contract-server'"
echo ""
echo "访问地址: http://${SERVER_HOST}:5032"
echo ""
