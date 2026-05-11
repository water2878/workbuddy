"""
合同审批独立服务器 — 部署到 Windows Server
功能：
1. 合同审批网页（公网访问）
2. 合同 CRUD API
3. PDF 生成（COM自动化）
4. 合同汇总统计
5. 合同修改（全状态可编辑+修订标记）
6. 与本地微信助手同步（推送/回调）
7. 产品图片管理（通过 materials_api 模块）

启动：python contract_server.py
端口：80（公网直接访问）或 5032
"""

import os
import sys
import json
import uuid
import shutil
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from product_kb import extract_product_params, get_standard_price
except ImportError:
    extract_product_params = None
    get_standard_price = None

# 导入产品图片管理模块
try:
    from materials_api import handle_request as handle_materials_request
except ImportError:
    handle_materials_request = None

# ========== 配置 - 独立部署版本：路径相对于当前文件目录 ==========
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONTRACTS_DIR = os.path.join(BASE_DIR, "data", "contracts")
PENDING_DIR = os.path.join(CONTRACTS_DIR, "pending")
APPROVED_DIR = os.path.join(CONTRACTS_DIR, "approved")
SENT_DIR = os.path.join(CONTRACTS_DIR, "sent")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_DIR = os.path.join(CONTRACTS_DIR, "images")
WEB_DIR = os.path.join(BASE_DIR, "web")

# 字段名称映射（用于修改记录显示）
_field_names = {
    "customer_name": "客户名称",
    "customer_contact": "联系人",
    "customer_phone": "联系电话",
    "customer_address": "收货地址",
    "delivery_date": "交货日期",
    "payment_terms": "付款方式",
    "notes": "备注",
    "order_no": "订单号",
    "order_date": "下单日期",
    "total_amount": "合同总额",
    "products": "产品清单",
    "voltage": "电压规格",
    "plug_type": "插头类型",
    "shipping_country": "发货国家",
}

# 确保目录存在
for d in [CONTRACTS_DIR, PENDING_DIR, APPROVED_DIR, SENT_DIR, TEMPLATE_DIR, UPLOADS_DIR]:
    os.makedirs(d, exist_ok=True)

SERVER_PORT = int(os.environ.get("CONTRACT_PORT", "5032"))
API_TOKEN = os.environ.get("API_TOKEN", "")
CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
CALLBACK_TOKEN = os.environ.get("CALLBACK_TOKEN", "")

print(f"[配置] 产品图片管理模块: {'已加载' if handle_materials_request else '未加载'}")
