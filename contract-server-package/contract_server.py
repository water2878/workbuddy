"""
合同审批独立服务器 — 部署到 Windows Server
功能：
1. 合同审批网页（公网访问）
2. 合同 CRUD API
3. PDF 生成（COM自动化）
4. 合同汇总统计
5. 合同修改（全状态可编辑+修订标记）
6. 与本地微信助手同步（推送/回调）

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

# ═══════════════════════════════════════════════════════
# 日志工具 - 统一使用 core.config.log
# ═══════════════════════════════════════════════════════
try:
    from core.config import log
except ImportError:
    # 兜底日志函数
    def log(msg, tag="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{tag}] {msg}", flush=True)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from product_kb import extract_product_params, get_standard_price, get_all_model_codes, is_valid_model, PANEL_MODELS
except ImportError:
    extract_product_params = None
    get_standard_price = None
    get_all_model_codes = lambda: []
    is_valid_model = lambda model: True
    PANEL_MODELS = ["E0", "E1"]

# 导入产品图片管理模块
try:
    from materials_api import handle_request as handle_materials_request
except ImportError:
    handle_materials_request = None

# 导入客户无忧模块
try:
    from customers_api import handle_request as handle_customers_request
except ImportError:
    handle_customers_request = None

# ========== 配置 - 独立部署版本：路径相对于当前文件目录 ==========
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 产品图片目录配置
PRODUCT_IMAGES_DIR = os.path.join(BASE_DIR, "assets", "images")
os.makedirs(PRODUCT_IMAGES_DIR, exist_ok=True)
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
    "company_name": "公司名称",
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

# ========== 数据模型 ==========

class ContractStatus(Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


@dataclass
class OrderInfo:
    company_name: str = ""  # 公司名称（乙方）
    customer_contact: str = ""  # 联系人
    customer_phone: str = ""  # 联系电话
    customer_address: str = ""  # 收货地址
    products: List[Dict[str, Any]] = field(default_factory=list)
    order_no: str = ""
    order_date: str = ""
    delivery_date: str = ""
    payment_terms: str = ""
    voltage: str = "220V/50Hz"
    plug_type: str = "国标/欧规/美规"
    shipping_country: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "OrderInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RevisionRecord:
    at: str = ""
    by: str = ""
    reason: str = ""
    changes: str = ""


@dataclass
class Contract:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    status: ContractStatus = ContractStatus.DRAFT
    session_id: str = ""
    customer_wxid: str = ""
    customer_nickname: str = ""
    agent_id: str = ""
    order: OrderInfo = field(default_factory=OrderInfo)
    pdf_path: str = ""
    xlsx_path: str = ""
    created_at: str = ""
    approved_at: str = ""
    sent_at: str = ""
    approved_by: str = ""
    reject_reason: str = ""
    revisions: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, ContractStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "Contract":
        if isinstance(data.get("status"), str):
            data["status"] = ContractStatus(data["status"])
        if isinstance(data.get("order"), dict):
            data["order"] = OrderInfo.from_dict(data["order"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ========== 合同存储 ==========

_contracts_cache: Dict[str, Contract] = {}
_contracts_cache_time: float = 0
_contracts_lock = threading.Lock()
_save_queue: List[Dict[str, Contract]] = []
_save_timer: Optional[threading.Timer] = None
_save_lock = threading.Lock()
SAVE_DELAY = 0.5  # 延迟保存时间（秒）

def _get_contracts_file() -> str:
    return os.path.join(CONTRACTS_DIR, "contracts.json")


def load_contracts() -> Dict[str, Contract]:
    global _contracts_cache, _contracts_cache_time
    fpath = _get_contracts_file()
    
    if not os.path.exists(fpath):
        return {}
    
    try:
        mtime = os.path.getmtime(fpath)
        with _contracts_lock:
            if mtime <= _contracts_cache_time and _contracts_cache:
                return _contracts_cache
            
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    _contracts_cache = {}
                    _contracts_cache_time = mtime
                    return {}
                data = json.loads(content)
                _contracts_cache = {k: Contract.from_dict(v) for k, v in data.items()}
                _contracts_cache_time = mtime
                return _contracts_cache
    except (json.JSONDecodeError, IOError, OSError) as e:
        log(f"合同加载失败: {e}", "ERROR")
        return {}


def _do_save_contracts(contracts: Dict[str, Contract]):
    """实际执行保存操作"""
    global _contracts_cache, _contracts_cache_time
    fpath = _get_contracts_file()
    temp_path = fpath + ".tmp"
    try:
        # 先写入临时文件，避免写入过程中损坏原文件
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in contracts.items()}, f, ensure_ascii=False, indent=2, default=str)
        
        # 原子替换
        shutil.move(temp_path, fpath)
        
        with _contracts_lock:
            _contracts_cache = contracts.copy()
            _contracts_cache_time = os.path.getmtime(fpath)
        log(f"合同保存成功: {len(contracts)} 条记录", "合同")
    except Exception as e:
        log(f"合同保存失败: {e}", "ERROR")
        # 清理临时文件
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def save_contracts(contracts: Dict[str, Contract], immediate: bool = False):
    """
    保存合同数据
    immediate: 是否立即保存，否则延迟批量保存
    """
    global _save_queue, _save_timer
    
    with _save_lock:
        # 更新队列中的数据
        _save_queue.append(contracts.copy())
        
        # 取消之前的定时器
        if _save_timer:
            _save_timer.cancel()
        
        if immediate:
            # 立即保存
            latest = _save_queue[-1] if _save_queue else contracts
            _save_queue.clear()
            _do_save_contracts(latest)
        else:
            # 延迟保存，合并多次修改
            def delayed_save():
                global _save_queue, _save_timer
                with _save_lock:
                    if _save_queue:
                        # 使用最新的数据
                        latest = _save_queue[-1]
                        _save_queue.clear()
                        _save_timer = None
                        _do_save_contracts(latest)
            
            _save_timer = threading.Timer(SAVE_DELAY, delayed_save)
            _save_timer.daemon = True
            _save_timer.start()


def update_contract_field(contract_id: str, **fields):
    contracts = load_contracts()
    if contract_id not in contracts:
        return False
    c = contracts[contract_id]
    for k, v in fields.items():
        if hasattr(c, k):
            setattr(c, k, v)
    save_contracts(contracts)
    return True


# ========== PDF 生成 ==========

def _auto_font_size(cell, min_size=7, default_size=9):
    try:
        text = str(cell.Value) if cell.Value else ""
        if not text or len(text) <= 1:
            cell.Font.Size = default_size
            return
        est_width = sum(7.5 if ord(c) > 127 else 5 for c in text)
        avail_width = cell.Width - 4
        if est_width <= avail_width:
            cell.Font.Size = default_size
            return
        ratio = avail_width / est_width
        new_size = max(min_size, int(default_size * ratio))
        cell.Font.Size = new_size
    except Exception:
        pass


def generate_order_no() -> str:
    return f"CT{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _parse_notes_and_add_panel(order: OrderInfo) -> None:
    """从notes中解析颜色、面板信息，并添加面板作为独立产品"""
    notes = order.notes or ""
    
    # 解析颜色（黑色/白色）
    frame_color = ""
    if notes and "黑色" in notes:
        frame_color = "黑色"
    elif notes and "白色" in notes:
        frame_color = "白色"
    
    # 解析面板等级和尺寸
    panel_type = ""  # E0/E1
    panel_size = ""  # 1.4*0.7米 或 1400*700mm*25mm 等
    
    if notes:
        if "E0" in notes.upper() or "e0" in notes:
            panel_type = "E0级"
        elif "E1" in notes.upper() or "e1" in notes:
            panel_type = "E1级"
        
        # 匹配尺寸格式：
        # 1. 带厚度：1400*700mm*25mm、1400*700*25mm、1.4*0.7米*25mm
        # 2. 不带厚度：1.4*0.7米、1400*700mm
        size_match = re.search(r'(\d+(?:\.\d+)?)\s*[\*xX]\s*(\d+(?:\.\d+)?)\s*(米|mm)?\s*(?:\*\s*(\d+)\s*(mm)?)?', notes)
        if size_match:
            w, h, unit, thick, thick_unit = size_match.groups()
            if unit == '米' or (not unit and '.' in w):
                # 使用米为单位：1.4*0.7米
                panel_size = f"{w}*{h}米"
            else:
                # 使用mm为单位：1400*700mm
                panel_size = f"{w}*{h}mm"
            # 如果有厚度，追加厚度
            if thick:
                panel_size += f"*{thick}mm"
    
    # 更新现有产品的frame_color
    for prod in order.products:
        if frame_color and not prod.get('frame_color'):
            prod['frame_color'] = frame_color
    
    # 检查是否已有面板产品，如果有则补充frame_size
    for prod in order.products:
        model = prod.get('model', '')
        if model and model.upper() in [p.upper() for p in PANEL_MODELS]:
            # 这是面板产品，检查是否需要补充frame_size
            if not prod.get('frame_size') and panel_size:
                prod['frame_size'] = panel_size
                log(f"为面板产品 {model} 补充尺寸: {panel_size}", "面板")
            # 补充描述信息
            if not prod.get('description') and panel_type:
                prod['description'] = f'{panel_type}刨花板桌面'
            # 补充备注信息
            if not prod.get('remark') and panel_type:
                prod['remark'] = f'{panel_type}环保等级'
    
    # 如果有面板信息但没有面板产品，添加面板作为独立产品
    if panel_type and panel_size:
        # 检查是否已存在该面板型号
        existing_panel = False
        for prod in order.products:
            model = prod.get('model', '')
            if model and model.upper() == panel_type.replace('级', '').upper():
                existing_panel = True
                break
        
        if not existing_panel:
            # 获取面板数量（与桌架相同）- 排除面板型号本身
            panel_qty = 0
            for prod in order.products:
                model = prod.get('model', '')
                # 排除面板型号，其他都认为是桌架
                if model and model not in PANEL_MODELS:
                    panel_qty = prod.get('quantity', 1)
                    break
            
            if panel_qty > 0:
                # 根据尺寸确定单价
                price_map = {
                    "1.2*0.6": 90, "1.4*0.7": 218, "1.6*0.8": 244,
                    "1.6*0.7": 244, "1.8*0.8": 244
                }
                unit_price = 0
                for size_key, price in price_map.items():
                    if size_key in panel_size or panel_size in size_key:
                        unit_price = price
                        break
                # 默认价格
                if unit_price == 0:
                    unit_price = 218
                
                # E0比E1贵一点
                if panel_type == "E0级":
                    unit_price += 3
                
                panel_product = {
                    'name': f'{panel_type}刨花板面板',
                    'model': panel_type.replace('级', ''),  # E0级 -> E0
                    'description': f'{panel_type}刨花板桌面',
                    'frame_size': panel_size,
                    'quantity': panel_qty,
                    'unit_price': unit_price,
                    'subtotal': unit_price * panel_qty,
                    'frame_color': '定制',
                    'remark': f'{panel_type}环保等级'
                }
                order.products.append(panel_product)


def generate_pdf(contract: Contract) -> tuple:
    template_xlsx = os.path.join(TEMPLATE_DIR, "精亚国际贸易发展有限公司.xlsx")
    if not os.path.exists(template_xlsx):
        log(f"模板不存在: {template_xlsx}", "ERROR")
        return "", ""

    try:
        pdf_path, xlsx_path = _generate_from_xlsx_fill(contract, template_xlsx)
        return pdf_path, xlsx_path
    except Exception as e:
        log(f"生成失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return "", ""


def _generate_from_xlsx_fill(contract: Contract, template_path: str) -> tuple:
    order = contract.order
    base_name = f"合同_{order.order_no}_{contract.customer_nickname or '客户'}"
    xlsx_path = os.path.join(PENDING_DIR, base_name + ".xlsx")
    pdf_path = os.path.join(PENDING_DIR, base_name + ".pdf")

    try:
        import win32com.client
        import pythoncom
        import subprocess
        
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)

        for proc_name in ["et.exe", "wps.exe", "excel.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc_name],
                             capture_output=True, timeout=5)
            except:
                pass

        time.sleep(1)

        excel = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
        except:
            try:
                excel = win32com.client.DispatchEx("WPS.Application")
            except:
                try:
                    excel = win32com.client.DispatchEx("Ket.Application")
                except:
                    raise Exception("无法启动Excel或WPS")
        
        excel.Visible = False
        excel.DisplayAlerts = False

        wb = excel.Workbooks.Open(os.path.abspath(template_path))
        ws = wb.ActiveSheet

        try:
            if ws.ProtectContents or ws.ProtectionMode:
                log("工作表已保护，尝试解除...", "PDF")
                ws.Unprotect()
                log("工作表保护解除成功", "PDF")
            else:
                log("工作表未保护", "PDF")
        except Exception as prot_err:
            log(f"检查/解除保护失败: {prot_err}", "WARN")
            try:
                ws.Unprotect("")
            except:
                pass

        excel.Calculation = -4135

        def _safe_set(cell_ref, value, max_retries=3):
            for attempt in range(max_retries):
                try:
                    ws.Range(cell_ref).Value = value
                    return
                except Exception as e2:
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    log(f"写入 {cell_ref} 失败: {e2}", "WARN")
                    try:
                        import re as _re
                        m = _re.match(r'([A-Z]+)(\d+)', str(cell_ref))
                        if m:
                            col_str, row_num = m.group(1), int(m.group(2))
                            col_num = 0
                            for c in col_str:
                                col_num = col_num * 26 + (ord(c) - ord('A') + 1)
                            ws.Cells(row_num, col_num).Value = value
                            return
                    except Exception as e3:
                        log(f"Cells方式也失败: {e3}", "WARN")

        date_str = order.order_date or datetime.now().strftime('%Y-%m-%d')

        # 优先使用公司名称(company_name)，如果没有则使用微信昵称(customer_nickname)
        company_display = order.company_name.strip() if order.company_name and order.company_name.strip() else (contract.customer_nickname or '')
        _safe_set("F3", f"  乙方：{company_display}")
        # 联系人和电话只取最后一个（最新的）
        contact_display = order.customer_contact.split('/')[-1].strip() if order.customer_contact and '/' in order.customer_contact else (order.customer_contact or '')
        phone_display = order.customer_phone.split('/')[-1].strip() if order.customer_phone and '/' in order.customer_phone else (order.customer_phone or '')
        _safe_set("F4", f"  联系人：{contact_display}")
        _safe_set("F5", f"  电话：{phone_display}")
        _safe_set("F6", f"  地址：{order.customer_address or ''}")
        _safe_set("A8", f"  下单日期：{date_str}")
        _safe_set("F8", f"单号：{order.order_no}")

        products = order.products or []
        total_amount = 0
        total_qty = 0

        insert_count = max(0, len(products) - 1)
        if insert_count > 0:
            try:
                ws.Range(f"11:{10 + insert_count}").Insert(Shift=-4121)
            except Exception as e_ins:
                log(f"插入行失败: {e_ins}", "WARN")
                for _ in range(insert_count):
                    try:
                        ws.Rows(11).Insert(Shift=-4121)
                    except:
                        pass

        for i, prod in enumerate(products):
            row = 11 + i
            qty = int(prod.get('quantity', 1))
            price = float(prod.get('unit_price', 0))
            if price <= 0 and get_standard_price and prod.get('model'):
                price = get_standard_price(prod.get('model'))
            sub = float(prod.get('subtotal') or price * qty)
            total_amount += sub
            total_qty += qty

            kb_params = {}
            if extract_product_params and prod.get('model'):
                kb_params = extract_product_params(prod.get('model'))

            try:
                ws.Cells(row, 1).Value = i + 1
            except:
                _safe_set(f"A{row}", i + 1)

            _model_val = prod.get('model', '') or ''
            _safe_set(f"C{row}", _model_val)
            if 'model' not in prod or not prod['model']:
                prod['model'] = _model_val

            # 处理面板型号的描述
            _desc = prod.get('description', '')
            if not _desc:
                # 检查是否是面板型号
                if _model_val.upper() in [p.upper() for p in PANEL_MODELS]:
                    _desc = f'{_model_val}级刨花板面板'
                else:
                    _desc = kb_params.get('description', '') or '智能升降桌'
            _safe_set(f"D{row}", _desc)
            if not prod.get('description'):
                prod['description'] = _desc

            # 优先使用推送的数据，没有则使用知识库（桌架）或notes解析（面板）
            _model_val_upper = _model_val.upper()
            # 先检查产品自身是否有frame_size（推送的数据优先）
            _frame_size = prod.get('frame_size', '')
            if not _frame_size:
                # 没有推送数据，根据产品类型获取默认值
                if _model_val_upper in [p.upper() for p in PANEL_MODELS]:
                    # 面板产品：从notes解析（已在_parse_notes_and_add_panel中处理）
                    _frame_size = ''
                else:
                    # 桌架产品：从知识库获取
                    _frame_size = kb_params.get('frame_size', '')
            _safe_set(f"E{row}", _frame_size)
            if not prod.get('frame_size'):
                prod['frame_size'] = _frame_size

            _safe_set(f"F{row}", qty)

            _frame_color = prod.get('frame_color', '') or kb_params.get('color') or ''
            _safe_set(f"G{row}", _frame_color)
            if not prod.get('frame_color'):
                prod['frame_color'] = _frame_color

            if price > 0:
                _safe_set(f"H{row}", price)

            _volume = prod.get('unit_volume', '')
            if not _volume:
                volume_raw = kb_params.get('volume', '')
                vol_match = re.search(r'\(([\d.]+)m³\)', volume_raw)
                if vol_match:
                    _volume = f"{vol_match.group(1)}m³"
                else:
                    _volume = volume_raw
            if _volume:
                _safe_set(f"I{row}", _volume)
            if not prod.get('unit_volume') and _volume:
                prod['unit_volume'] = _volume

            _weight = prod.get('unit_weight', '') or kb_params.get('weight') or ''
            _safe_set(f"J{row}", _weight)
            if not prod.get('unit_weight'):
                prod['unit_weight'] = _weight

            _safe_set(f"K{row}", sub)
            _remark = prod.get('remark', '')
            _safe_set(f"L{row}", _remark)

            try:
                ws.Rows(row).AutoFit()
            except Exception as e_autofit:
                pass

            try:
                data_range = ws.Range(f"A{row}:L{row}")
                data_range.HorizontalAlignment = -4108
                data_range.VerticalAlignment = -4108
            except Exception as e_align:
                pass

            model = prod.get('model', '')
            img_paths = []
            prod_images = prod.get('images', [])
            
            log(f"产品{model}图片查找: {prod_images}", "PDF")
            
            if prod_images:
                for img_url in prod_images:
                    if img_url.startswith("/api/contracts/image/") or img_url.startswith("/contracts/images/"):
                        # URL解码：处理编码的特殊字符如括号 %28 %29
                        filename = unquote(img_url.split("/")[-1])
                        local_path = os.path.join(CONTRACTS_DIR, "images", filename)
                    elif img_url.startswith("assets/") or img_url.startswith("assets\\"):
                        local_path = os.path.join(BASE_DIR, img_url)
                    elif os.path.isabs(img_url):
                        local_path = img_url
                    else:
                        local_path = os.path.join(BASE_DIR, img_url)
                    if os.path.exists(local_path):
                        img_paths.append(os.path.abspath(local_path))
            
            if not img_paths and model:
                log(f"上传图片未找到，尝试型号目录: {model}", "PDF")
                img_dir = os.path.join(BASE_DIR, "assets", "images", model)
                if os.path.exists(img_dir):
                    img_files = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
                    if img_files:
                        img_files.sort()
                        img_paths.append(os.path.abspath(os.path.join(img_dir, img_files[0])))
                        log(f"从型号目录获取图片: {img_paths[-1]}", "PDF")
                else:
                    log(f"型号目录不存在: {img_dir}", "WARN")
            
            if img_paths:
                log(f"找到 {len(img_paths)} 张产品图片", "PDF")
            
            if img_paths:
                try:
                    COLS = 2
                    GAP = 4
                    PAD = 6
                    n = len(img_paths)

                    ws.Columns("B").ColumnWidth = 30
                    cell = ws.Range(f"B{row}")
                    cl = cell.Left
                    ct = cell.Top
                    cw = cell.Width

                    avail_w_per_pic = (cw - PAD * 2 - (COLS - 1) * GAP) / COLS
                    target_pic_w = min(avail_w_per_pic, 100)
                    target_pic_h = 75

                    inserted_pics = []
                    for img_path in img_paths:
                        pic = ws.Pictures().Insert(img_path)
                        if pic.Width > 0 and pic.Height > 0:
                            w_r = target_pic_w / pic.Width
                            h_r = target_pic_h / pic.Height
                            ratio = min(w_r, h_r)
                        else:
                            ratio = 1
                        fw = int(pic.Width * ratio)
                        fh = int(pic.Height * ratio)
                        pic.Width = fw
                        pic.Height = fh
                        inserted_pics.append((pic, fw, fh))

                    n_rows = max(1, (len(inserted_pics) + COLS - 1) // COLS)
                    content_h = n_rows * (inserted_pics[0][2] if inserted_pics else target_pic_h) + (n_rows - 1) * GAP
                    ws.Rows(row).RowHeight = max(int(content_h) + PAD * 2, 60)
                    ch = ws.Rows(row).RowHeight

                    content_h_actual = n_rows * (inserted_pics[0][2] if inserted_pics else target_pic_h) + (n_rows - 1) * GAP

                    for pi, (pic, pw, ph) in enumerate(inserted_pics):
                        c = pi % COLS
                        r = pi // COLS
                        if n == 1:
                            pic.Left = cl + (cw - pw) / 2
                            pic.Top = ct + (ch - ph) / 2
                        else:
                            row_n = min(n - r * COLS, COLS)
                            row_w = row_n * pw + (row_n - 1) * GAP
                            rx = cl + (cw - row_w) / 2 + c * (pw + GAP)
                            ry = ct + (ch - content_h_actual) / 2 + r * (ph + GAP)
                            pic.Left = max(cl + PAD, rx)
                            pic.Top = ry
                except Exception as pic_err:
                    log(f"插入产品图片失败: {pic_err}", "WARN")

        total_row = 11 + len(products)
        _safe_set(f"K{total_row}", None)
        try: ws.Cells(total_row, 1).Value = len(products) + 1
        except: _safe_set(f"A{total_row}", len(products) + 1)
        _safe_set(f"B{total_row}", "合计：")
        _safe_set(f"K{total_row}", float(total_amount))

        try:
            total_range = ws.Range(f"A{total_row}:K{total_row}")
            total_range.HorizontalAlignment = -4108
            total_range.VerticalAlignment = -4108
        except Exception as e_tr:
            pass

        terms_offset = insert_count
        notes_row = 13 + terms_offset
        deposit_row = 15 + terms_offset
        payment_row = 16 + terms_offset
        
        # 填写备注（A列，"备注："红色，内容黑色）
        if order.notes:
            try:
                # 获取原有内容（包含红色"备注："）
                orig_value = ws.Range(f"A{notes_row}").Value or ''
                if not orig_value.strip():
                    orig_value = '备注：'
                
                # 设置完整内容
                ws.Range(f"A{notes_row}").Value = f"{orig_value}{order.notes}"
                
                # 设置内容部分为黑色（"备注："保持红色）
                start_pos = len(orig_value)
                if start_pos > 0:
                    ws.Range(f"A{notes_row}").Characters(Start=start_pos+1, Length=len(order.notes)).Font.ColorIndex = 1
            except Exception as e:
                log(f"设置备注格式失败: {e}", "WARN")
                _safe_set(f"A{notes_row}", f"备注：{order.notes}")
        
        if total_amount > 0:
            deposit = int(total_amount * 0.45)
            _safe_set(f"B{deposit_row}", (
                f"（1）以上双方签定合同，购方应向供应方支付总货款45%，"
                f"即￥{deposit:,}元整，方可安排发货，收货待定   "
            ))
            if order.payment_terms:
                _safe_set(f"B{payment_row}", f"（2）付款方式：{order.payment_terms}")

        excel.Calculation = -4105

        sign_offset = len(products) - 1
        h_brand = 41 + sign_offset
        h_phone = 43 + sign_offset

        name_val = (order.company_name or contract.customer_nickname or '').replace('\n', ' ').replace('\r', ' ').strip()
        phone_val = (order.customer_phone or '').replace('\n', ' ').replace('\r', ' ').strip()

        if name_val:
            try:
                orig_brand = ws.Range(f"H{h_brand}").Value or ''
                _safe_set(f"H{h_brand}", f"{orig_brand} {name_val}")
            except:
                _safe_set(f"H{h_brand}", name_val)
        if phone_val:
            try:
                orig_phone = ws.Range(f"H{h_phone}").Value or ''
                _safe_set(f"H{h_phone}", f"{orig_phone} {phone_val}")
            except:
                _safe_set(f"H{h_phone}", phone_val)

        try:
            for i in range(len(products)):
                row = 11 + i
                current_h = ws.Rows(row).RowHeight
                ws.Rows(row).RowHeight = max(current_h, 80)
        except Exception as row_err:
            log(f"调整行高失败: {row_err}", "WARN")

        wb.SaveAs(os.path.abspath(xlsx_path), FileFormat=51)

        try:
            wb.ExportAsFixedFormat(0, os.path.abspath(pdf_path))
            log(f"PDF导出成功: {pdf_path}", "PDF")
            wb.Close()
            excel.Quit()
            pythoncom.CoUninitialize()
            return pdf_path, xlsx_path
        except Exception as e:
            log(f"PDF导出失败: {e}", "ERROR")
            wb.Close()
            excel.Quit()
            pythoncom.CoUninitialize()
            return "", xlsx_path

    except ImportError:
        log("win32com不可用，无法生成PDF", "ERROR")
        return "", ""
    except Exception as e:
        log(f"Excel COM操作失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        try:
            excel.Quit()
            pythoncom.CoUninitialize()
        except:
            pass
        return "", ""


# ========== 合同操作 ==========

# PDF 生成队列控制
_pdf_gen_lock = threading.Lock()
_pdf_gen_queue: List[str] = []
_pdf_gen_active: Dict[str, bool] = {}
MAX_CONCURRENT_PDF = 2  # 最大并发 PDF 生成数

def _generate_pdf_async(contract_id: str):
    """
    异步生成 PDF，使用队列控制并发数
    """
    with _pdf_gen_lock:
        if contract_id in _pdf_gen_queue or _pdf_gen_active.get(contract_id):
            log(f"合同 {contract_id} 已在队列中，跳过重复请求", "PDF")
            return
        _pdf_gen_queue.append(contract_id)
    
    def _process_queue():
        while True:
            with _pdf_gen_lock:
                # 检查并发数
                active_count = sum(1 for v in _pdf_gen_active.values() if v)
                if active_count >= MAX_CONCURRENT_PDF or not _pdf_gen_queue:
                    return
                
                cid = _pdf_gen_queue.pop(0)
                _pdf_gen_active[cid] = True
            
            try:
                _do_generate_single(cid)
            finally:
                with _pdf_gen_lock:
                    _pdf_gen_active[cid] = False
                # 继续处理队列
                threading.Thread(target=_process_queue, daemon=True).start()
    
    def _do_generate_single(cid: str):
        try:
            log(f"开始生成PDF: {cid}", "PDF")
            contracts = load_contracts()
            if cid not in contracts:
                log(f"合同已不存在: {cid}", "PDF")
                return
            contract = contracts[cid]
            
            pdf_path, xlsx_path = generate_pdf(contract)

            if pdf_path and os.path.exists(pdf_path):
                contract.pdf_path = pdf_path
                contract.xlsx_path = xlsx_path
                contracts[cid] = contract
                # PDF 生成完成后再保存，使用延迟保存
                save_contracts(contracts, immediate=False)
                log(f"PDF生成成功: {cid}", "PDF")
            else:
                log(f"PDF生成失败: {cid}", "ERROR")
        except Exception as e:
            log(f"PDF生成异常: {cid} - {e}", "ERROR")
            import traceback
            traceback.print_exc()
    
    # 启动队列处理
    threading.Thread(target=_process_queue, daemon=True, name=f"pdf-queue-processor").start()


def create_contract(order_data: Dict) -> Optional[Contract]:
    """创建合同 - 数据已由本地解析完成，云端直接生成"""
    order = OrderInfo.from_dict(order_data) if isinstance(order_data, dict) else order_data
    if not order.order_no:
        order.order_no = generate_order_no()
    
    # 云端补充：解析notes中的面板信息，为已存在的面板产品补充frame_size等字段
    _parse_notes_and_add_panel(order)
    log(f"创建合同: {order.order_no}, 产品数: {len(order.products)}", "合同")
    for prod in order.products:
        log(f"  产品: {prod.get('model')} - {prod.get('frame_size', '无尺寸')}", "合同")

    contract = Contract(
        id=order.order_no,
        session_id=order_data.get("session_id", ""),
        customer_wxid=order_data.get("customer_wxid", ""),
        customer_nickname=order_data.get("customer_nickname", ""),
        agent_id=order_data.get("agent_id", ""),
        order=order,
        status=ContractStatus.PENDING,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    contracts = load_contracts()
    contracts[contract.id] = contract
    # 立即保存新合同，确保数据不丢失
    save_contracts(contracts, immediate=True)
    _notify_sse_clients()

    # PDF 生成改为完全异步，不阻塞响应
    import threading
    t = threading.Thread(target=_generate_pdf_async, args=(contract.id,), daemon=True)
    t.start()

    return contract


def approve_contract(contract_id: str, approver: str = "管理员") -> bool:
    log(f"开始审批合同: {contract_id}, 审批人: {approver}", "审批")
    contracts = load_contracts()
    if contract_id not in contracts:
        log(f"合同不存在: {contract_id}", "ERROR")
        return False

    contract = contracts[contract_id]
    contract.status = ContractStatus.APPROVED
    contract.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contract.approved_by = approver

    log(f"合同状态已更新: {contract_id} -> APPROVED", "审批")

    if contract.pdf_path and os.path.exists(contract.pdf_path):
        new_path = os.path.join(APPROVED_DIR, os.path.basename(contract.pdf_path))
        shutil.move(contract.pdf_path, new_path)
        contract.pdf_path = new_path
        log(f"PDF已移动到: {new_path}", "审批")

    # 状态变更立即保存，确保前端及时看到
    save_contracts(contracts, immediate=True)
    _notify_sse_clients()
    _notify_agent_sse(contract_id, "approved", contract.agent_id, {
        "customer_wxid": contract.customer_wxid,
        "customer_nickname": contract.customer_nickname,
        "session_id": contract.session_id,
        "pdf_url": f"/api/contracts/pdf/{contract_id}"
    })
    _notify_callback(contract_id, "approved", approver)
    log(f"合同审批完成: {contract_id}", "审批")
    return True


def reject_contract(contract_id: str, reason: str = "") -> bool:
    log(f"开始拒绝合同: {contract_id}, 原因: {reason}", "拒绝")
    contracts = load_contracts()
    if contract_id not in contracts:
        log(f"合同不存在: {contract_id}", "ERROR")
        return False

    contract = contracts[contract_id]
    contract.status = ContractStatus.REJECTED
    contract.reject_reason = reason
    log(f"合同状态已更新: {contract_id} -> REJECTED", "拒绝")
    
    # 状态变更立即保存
    save_contracts(contracts, immediate=True)

    _notify_sse_clients()
    _notify_agent_sse(contract_id, "rejected", contract.agent_id, {
        "reason": reason
    })
    _notify_callback(contract_id, "rejected", reason=reason)
    log(f"合同拒绝完成: {contract_id}", "拒绝")
    return True


def update_contract(contract_id: str, updates: Dict[str, Any], modifier: str = "管理员") -> Optional[Contract]:
    contracts = load_contracts()
    if contract_id not in contracts:
        return None

    contract = contracts[contract_id]
    old_status = contract.status

    # 保存旧值用于记录修改
    old_order_dict = asdict(contract.order)
    order_dict = asdict(contract.order)
    
    # 记录具体修改内容
    changes_detail = []
    
    product_field_names = {
        "model": "型号",
        "description": "描述",
        "frame_size": "尺寸",
        "frame_color": "颜色",
        "quantity": "数量",
        "unit_price": "单价",
        "unit_volume": "体积",
        "unit_weight": "重量",
        "subtotal": "小计",
        "remark": "备注",
        "images": "图片",
    }
    
    for key, value in updates.items():
        if key in order_dict:
            old_value = old_order_dict.get(key, "")
            new_value = value
            
            if key == "products":
                old_products = old_value if isinstance(old_value, list) else []
                new_products = new_value if isinstance(new_value, list) else []
                
                def format_single_product(p):
                    if isinstance(p, dict):
                        model = p.get("model", p.get("name", "未知型号"))
                        qty = p.get("quantity", 1)
                        price = p.get("unit_price", 0)
                        return f"{model}×{qty}(¥{price})"
                    return str(p)
                
                added = []
                removed = []
                modified = []
                
                old_models = {p.get("model", str(i)): (i, p) for i, p in enumerate(old_products) if isinstance(p, dict)}
                new_models = {p.get("model", str(i)): (i, p) for i, p in enumerate(new_products) if isinstance(p, dict)}
                
                for model in new_models:
                    if model not in old_models:
                        added.append(format_single_product(new_models[model][1]))
                    else:
                        old_p = old_models[model][1]
                        new_p = new_models[model][1]
                        field_changes = []
                        all_fields = set(list(old_p.keys()) + list(new_p.keys()))
                        for field in all_fields:
                            old_val = old_p.get(field, "")
                            new_val = new_p.get(field, "")
                            if str(old_val) != str(new_val):
                                field_name = product_field_names.get(field, field)
                                if field == "images":
                                    old_count = len(old_val) if isinstance(old_val, list) else 0
                                    new_count = len(new_val) if isinstance(new_val, list) else 0
                                    field_changes.append(f"{field_name}: {old_count}张 → {new_count}张")
                                else:
                                    old_str = str(old_val)[:20]
                                    new_str = str(new_val)[:20]
                                    field_changes.append(f"{field_name}: {old_str} → {new_str}")
                        if field_changes:
                            modified.append(f"{new_p.get('model', '未知')}[{', '.join(field_changes)}]")
                
                for model in old_models:
                    if model not in new_models:
                        removed.append(format_single_product(old_models[model][1]))
                
                product_changes = []
                if added:
                    product_changes.append(f"新增: {', '.join(added)}")
                if removed:
                    product_changes.append(f"删除: {', '.join(removed)}")
                if modified:
                    product_changes.append(f"修改: {', '.join(modified)}")
                
                if product_changes:
                    changes_detail.append(f"产品清单: {' | '.join(product_changes)}")
            else:
                old_str = str(old_value)[:50] + ("..." if len(str(old_value)) > 50 else "")
                new_str = str(new_value)[:50] + ("..." if len(str(new_value)) > 50 else "")
                
                if str(old_value) != str(new_value):
                    changes_detail.append(f"{_field_names.get(key, key)}: {old_str} → {new_str}")
            
            order_dict[key] = value
    contract.order = OrderInfo.from_dict(order_dict)

    needs_reapproval = old_status in (ContractStatus.APPROVED, ContractStatus.SENT)
    if needs_reapproval:
        contract.status = ContractStatus.PENDING
        contract.approved_at = ""
        contract.approved_by = ""

    # 生成修改摘要
    if changes_detail:
        change_summary = "; ".join(changes_detail)
    else:
        change_summary = "未修改字段"
    
    contract.revisions = contract.revisions or []
    contract.revisions.append({
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "by": modifier,
        "reason": updates.get("_reason", "编辑修改"),
        "changes": change_summary
    })

    # 清除旧PDF路径，标记为需要重新生成
    old_pdf_path = contract.pdf_path
    old_xlsx_path = contract.xlsx_path
    contract.pdf_path = ""
    contract.xlsx_path = ""
    
    contracts[contract_id] = contract
    # 合同数据立即保存，确保前端能立即看到状态
    save_contracts(contracts, immediate=True)

    # 异步删除旧文件和生成新 PDF
    def _regenerate_pdf_async():
        # 删除旧文件
        for old_path in [old_pdf_path, old_xlsx_path]:
            if old_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except:
                    pass
        
        log(f"编辑后重新生成PDF: {contract_id}", "合同")
        pdf_path, xlsx_path = "", ""
        try:
            pdf_path, xlsx_path = generate_pdf(contract)
            log(f"编辑重新生成PDF成功: {contract_id}", "合同")
        except Exception as e:
            log(f"编辑重新生成PDF失败: {contract_id} - {e}", "ERROR")

        if pdf_path:
            contract.pdf_path = pdf_path
            contract.xlsx_path = xlsx_path
        else:
            contract.pdf_path = ""
            contract.xlsx_path = ""
            log(f"编辑后PDF路径为空: {contract_id}", "ERROR")
        
        # PDF生成完成后再保存一次（延迟保存）
        contracts[contract_id] = contract
        save_contracts(contracts, immediate=False)
    
    # 启动异步线程处理 PDF 重新生成
    threading.Thread(target=_regenerate_pdf_async, daemon=True).start()
    
    return contract


def mark_sent(contract_id: str) -> bool:
    contracts = load_contracts()
    if contract_id not in contracts:
        return False

    contract = contracts[contract_id]
    contract.status = ContractStatus.SENT
    contract.sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if contract.pdf_path and os.path.exists(contract.pdf_path):
        new_path = os.path.join(SENT_DIR, os.path.basename(contract.pdf_path))
        shutil.move(contract.pdf_path, new_path)
        contract.pdf_path = new_path

    # 状态变更立即保存
    save_contracts(contracts, immediate=True)
    _notify_callback(contract_id, "sent")
    return True


def get_pending_contracts() -> List['Contract']:
    """获取待审批合同列表"""
    contracts = load_contracts()
    return [c for c in contracts.values() if c.status == ContractStatus.PENDING]


# ========== 汇总统计 ==========

def get_summary(status_filter: str = "all", date_from: str = "", date_to: str = "") -> Dict:
    contracts = load_contracts()
    all_contracts = list(contracts.values())

    if date_from:
        all_contracts = [c for c in all_contracts if c.created_at >= date_from]
    if date_to:
        all_contracts = [c for c in all_contracts if c.created_at <= date_to + " 23:59:59"]

    if status_filter != "all":
        all_contracts = [c for c in all_contracts if c.status.value == status_filter]

    total_count = len(all_contracts)
    def _safe_subtotal(p):
        s = p.get("subtotal", 0)
        try:
            return float(s) if s else 0
        except (ValueError, TypeError):
            return 0
    total_amount = sum(sum(_safe_subtotal(p) for p in c.order.products) for c in all_contracts)

    by_status = {}
    for c in all_contracts:
        st = c.status.value
        by_status[st] = by_status.get(st, 0) + 1

    by_month = {}
    for c in all_contracts:
        month = (c.created_at or "")[:7]
        if month:
            if month not in by_month:
                by_month[month] = {"month": month, "count": 0, "amount": 0}
            by_month[month]["count"] += 1
            by_month[month]["amount"] += sum(_safe_subtotal(p) for p in c.order.products)

    by_customer = {}
    for c in all_contracts:
        name = c.order.company_name or c.customer_nickname or "未知"
        if name not in by_customer:
            by_customer[name] = {"name": name, "count": 0, "amount": 0, "latest": ""}
        by_customer[name]["count"] += 1
        by_customer[name]["amount"] += sum(_safe_subtotal(p) for p in c.order.products)
        if c.created_at > (by_customer[name]["latest"] or ""):
            by_customer[name]["latest"] = c.created_at

    by_product = {}
    for c in all_contracts:
        for p in (c.order.products or []):
            model = p.get("model", "未知")
            if model not in by_product:
                by_product[model] = {"model": model, "count": 0, "amount": 0, "contracts": 0}
            by_product[model]["count"] += int(p.get("quantity", 0) or 0)
            by_product[model]["amount"] += _safe_subtotal(p)
            by_product[model]["contracts"] += 1

    return {
        "total_count": total_count,
        "total_amount": total_amount,
        "by_status": by_status,
        "by_month": sorted(by_month.values(), key=lambda x: x["month"], reverse=True),
        "by_customer": sorted(by_customer.values(), key=lambda x: x["amount"], reverse=True),
        "by_product": sorted(by_product.values(), key=lambda x: x["amount"], reverse=True),
    }


# ========== 回调通知 ==========

def _notify_callback(contract_id: str, action: str, approver: str = "", reason: str = ""):
    if not CALLBACK_URL:
        return

    try:
        import requests
        payload = {
            "contract_id": contract_id,
            "action": action,
            "approver": approver,
            "reason": reason,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        headers = {"Content-Type": "application/json"}
        if CALLBACK_TOKEN:
            headers["Authorization"] = f"Bearer {CALLBACK_TOKEN}"

        resp = requests.post(CALLBACK_URL, json=payload, headers=headers, timeout=10)
        log(f"回调 {action} {contract_id}: {resp.status_code}", "回调")
    except Exception as e:
        log(f"回调失败: {e}", "ERROR")


# ========== SSE 推送 ==========

_contract_sse_clients: set = set()
_agent_sse_clients: Dict = {}
_agent_sse_buffer: List = []
MAX_BUFFER_SIZE = 1000
_contract_sse_lock = threading.Lock()
_agent_sse_lock = threading.Lock()
_buffer_lock = threading.Lock()


def _notify_sse_clients():
    dead = set()
    with _contract_sse_lock:
        for wfile in list(_contract_sse_clients):
            try:
                wfile.write(b"data: update\n\n")
                wfile.flush()
            except:
                dead.add(wfile)
        _contract_sse_clients.difference_update(dead)


def _notify_agent_sse(contract_id: str, action: str, agent_id: str, extra: Dict = None):
    payload = {
        "contract_id": contract_id,
        "action": action,
        "agent_id": agent_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        payload.update(extra)

        with _buffer_lock:
            _agent_sse_buffer.append(payload)
            if len(_agent_sse_buffer) > MAX_BUFFER_SIZE:
                _agent_sse_buffer[:] = _agent_sse_buffer[-MAX_BUFFER_SIZE:]

        msg = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        msg_bytes = msg.encode("utf-8")

        dead = []
        with _agent_sse_lock:
            for wfile, sub_agent in list(_agent_sse_clients.items()):
                if sub_agent and agent_id and sub_agent != agent_id:
                    continue
                try:
                    wfile.write(msg_bytes)
                    wfile.flush()
                except:
                    dead.append(wfile)
            for wfile in dead:
                _agent_sse_clients.pop(wfile, None)


# ========== HTTP 服务器 ==========

class ContractHandler(BaseHTTPRequestHandler):

    def _check_auth(self) -> bool:
        if not API_TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == API_TOKEN
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        return params.get("access_token", [""])[0] == API_TOKEN

    def _find_product_image(self, model: str) -> str:
        if not model:
            return ""
        # 移除型号中的"-数字"后缀（如 T524-1 → T524）
        import re
        clean_model = re.sub(r'-\d+$', '', model)
        img_dir = os.path.join(BASE_DIR, "assets", "images", clean_model)
        if os.path.exists(img_dir):
            img_files = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
            if img_files:
                img_files.sort()
                return os.path.join(img_dir, img_files[0])
        return ""

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))

    def _send_file(self, filepath, content_type, filename=None):
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        if filename:
            ascii_name = quote(filename)
            self.send_header("Content-Disposition", f'inline; filename="contract.pdf"; filename*=UTF-8\'\'{ascii_name}')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.split("?")[0]
            full_path = self.path  # 保留完整路径（包含查询参数）

            # 处理产品图片管理 API（使用完整路径以支持分页参数）
            if handle_materials_request and handle_materials_request(self, "GET", full_path):
                return
            
            # 处理客户无忧 API（使用完整路径以支持分页参数）
            if handle_customers_request and handle_customers_request(self, "GET", full_path):
                return

            if path == "/" or path == "/contracts":
                self._serve_html()
                return

            if path == "/favicon.ico":
                self._serve_favicon()
                return

            if path == "/customers":
                self._serve_customers_html()
                return

            if path == "/materials":
                self._serve_materials_html()
                return

            if path == "/contracts.js":
                self._serve_js()
                return

            if path == "/pdf.worker.min.js":
                worker_path = os.path.join(WEB_DIR, "pdf.worker.min.js")
                if os.path.exists(worker_path):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    with open(worker_path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            if path.startswith("/contracts/images/"):
                fname = path.split("/")[-1]
                fpath = os.path.join(UPLOADS_DIR, fname)
                if os.path.exists(fpath):
                    ext = os.path.splitext(fname)[1].lower()
                    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext.lstrip("."), "image/jpeg")
                    self._send_file(fpath, ct)
                    return
                self._send_json({"error": "图片不存在"}, 404)
                return
            
            # 静态文件服务：提供 assets/images/ 下的文件（用于云端同步）
            if path.startswith("/assets/images/"):
                # 解码 URL 中的中文
                from urllib.parse import unquote
                decoded_path = unquote(path)
                # 构建文件路径
                file_path = os.path.join(BASE_DIR, decoded_path.lstrip("/"))
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    ext = os.path.splitext(file_path)[1].lower()
                    content_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext.lstrip("."), "application/octet-stream")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "max-age=86400")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
            
            # 文件下载 API：提供任意文件的下载（用于云端同步客户端）
            if path.startswith("/api/files/"):
                # 解码 URL 中的中文
                from urllib.parse import unquote
                decoded_path = unquote(path)
                # 提取文件路径（去掉 /api/files/ 前缀）
                file_rel_path = decoded_path[len("/api/files/"):]
                # 构建文件路径
                file_path = os.path.join(BASE_DIR, file_rel_path)
                # 安全检查：确保文件路径在 BASE_DIR 下
                real_file_path = os.path.realpath(file_path)
                real_base_dir = os.path.realpath(BASE_DIR)
                if not real_file_path.startswith(real_base_dir):
                    self.send_response(403)
                    self.end_headers()
                    return
                
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    ext = os.path.splitext(file_path)[1].lower()
                    content_type_map = {
                        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", 
                        "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
                        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "xls": "application/vnd.ms-excel", "doc": "application/msword",
                        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "txt": "text/plain", "json": "application/json"
                    }
                    content_type = content_type_map.get(ext.lstrip("."), "application/octet-stream")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "max-age=86400")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_response(404)
                    self.end_headers()
                    return

            # 注意：产品图片管理 API 已在上面通过 handle_materials_request 处理
            
            if not (path.startswith("/api/contracts/") or path == "/api/contracts"):
                if not self._check_auth():
                    self._send_json({"error": "unauthorized"}, 401)
                    return

            if path == "/api/contracts/list" or path == "/api/contracts/pending":
                params = parse_qs(parsed.query)
                status_filter = params.get("status", ["pending"])[0]
                date_from = params.get("from", [""])[0]
                date_to = params.get("to", [""])[0]
                search_keyword = params.get("search", [""])[0].lower()

                log(f"查询合同列表: status={status_filter}, keyword={search_keyword or '无'}", "查询")
                
                # 分页参数
                try:
                    page = int(params.get("page", ["1"])[0])
                except (ValueError, TypeError):
                    page = 1
                try:
                    page_size = int(params.get("page_size", ["10"])[0])
                except (ValueError, TypeError):
                    page_size = 10
                page_size = min(page_size, 100)  # 限制最大页大小
                
                contracts = load_contracts()

                if status_filter == "all":
                    filtered = list(contracts.values())
                else:
                    filtered = [c for c in contracts.values() if c.status.value == status_filter]

                if date_from:
                    filtered = [c for c in filtered if c.created_at >= date_from]
                if date_to:
                    filtered = [c for c in filtered if c.created_at <= date_to + " 23:59:59"]
                
                # 搜索过滤
                if search_keyword:
                    filtered = [c for c in filtered if 
                        search_keyword in (c.customer_nickname or "").lower() or
                        search_keyword in (c.order.company_name or "").lower() or
                        search_keyword in (c.order.order_no or "").lower() or
                        search_keyword in (c.order.customer_phone or "").lower() or
                        search_keyword in (c.agent_id or "").lower()
                    ]

                result = []
                for c in filtered:
                    total = sum(p.get("subtotal", 0) for p in c.order.products)
                    products = [f"{p.get('model','')}×{p.get('quantity',1)}" for p in c.order.products]
                    result.append({
                        "id": c.id,
                        "customer": c.customer_nickname or c.order.company_name or "未知",
                        "company_name": c.order.company_name or "",
                        "customer_nickname": c.customer_nickname or "",
                        "order_no": c.order.order_no,
                        "products": products,
                        "total_amount": total,
                        "pdf_path": c.pdf_path,
                        "xlsx_path": c.xlsx_path,
                        "created_at": c.created_at,
                        "approved_at": c.approved_at,
                        "sent_at": c.sent_at,
                        "approved_by": c.approved_by,
                        "customer_contact": c.order.customer_contact,
                        "customer_phone": c.order.customer_phone,
                        "customer_address": c.order.customer_address,
                        "payment_terms": c.order.payment_terms,
                        "notes": c.order.notes,
                        "status": c.status.value,
                        "reject_reason": c.reject_reason,
                        "revisions": c.revisions or [],
                        "agent_id": c.agent_id or "未知",
                    })

                result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                
                # 分页处理
                total = len(result)
                total_pages = (total + page_size - 1) // page_size if total > 0 else 1
                start = (page - 1) * page_size
                end = start + page_size
                paginated_result = result[start:end]
                
                log(f"查询结果: 共{total}条, 返回{len(paginated_result)}条", "查询")
                
                self._send_json({
                    "status": "ok", 
                    "count": len(paginated_result), 
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "contracts": paginated_result
                })

            elif path.startswith("/api/contracts/product-image/"):
                model = unquote(path.split("/")[-1])
                log(f"查询产品图片: {model}", "查询")
                img_path = self._find_product_image(model)
                if img_path and os.path.exists(img_path):
                    self.send_response(200)
                    ext = os.path.splitext(img_path)[1].lower()
                    content_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext, "image/jpeg")
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    with open(img_path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            elif path.startswith("/api/contracts/image/"):
                img_name = unquote(path.split("/")[-1])
                img_path = os.path.join(CONTRACTS_DIR, "images", img_name)
                if os.path.exists(img_path):
                    self.send_response(200)
                    ext = os.path.splitext(img_path)[1].lower()
                    content_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext, "image/jpeg")
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    with open(img_path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            elif path.startswith("/api/contracts/detail/"):
                contract_id = path.split("/")[-1]
                contracts = load_contracts()
                if contract_id not in contracts:
                    self._send_json({"error": "合同不存在"}, 404)
                    return
                c = contracts[contract_id]
                self._send_json({"status": "ok", "contract": c.to_dict()})

            elif path.startswith("/api/contracts/pdf/"):
                contract_id = path.split("/")[-1].split("?")[0]
                contracts = load_contracts()
                if contract_id not in contracts:
                    self._send_json({"error": "合同不存在"}, 404)
                    return
                c = contracts[contract_id]

                if not c.pdf_path or not os.path.exists(c.pdf_path):
                    base_name = f"合同_{c.order.order_no}_{c.customer_nickname or '客户'}"
                    possible_pdf = os.path.join(PENDING_DIR, base_name + ".pdf")
                    possible_xlsx = os.path.join(PENDING_DIR, base_name + ".xlsx")
                    if os.path.exists(possible_pdf):
                        log(f"发现已存在的PDF: {contract_id}", "PDF")
                        update_contract_field(contract_id, pdf_path=possible_pdf, xlsx_path=possible_xlsx if os.path.exists(possible_xlsx) else "")
                        c.pdf_path = possible_pdf
                    else:
                        log(f"按需生成PDF: {contract_id}", "PDF")
                        pdf_path, xlsx_path = generate_pdf(c)
                        if pdf_path and os.path.exists(pdf_path):
                            update_contract_field(contract_id, pdf_path=pdf_path, xlsx_path=xlsx_path)
                            c.pdf_path = pdf_path
                            c.xlsx_path = xlsx_path
                            log(f"按需生成PDF成功: {contract_id}", "PDF")
                        else:
                            diag = {
                                "error": "PDF生成失败",
                                "contract_id": contract_id,
                                "hint": "WPS COM可能未安装或模板缺失"
                            }
                            self._send_json(diag, 500)
                            return

                self._send_file(c.pdf_path, "application/pdf", os.path.basename(c.pdf_path))

            elif path == "/api/contracts/summary":
                params = parse_qs(parsed.query)
                status_filter = params.get("status", ["all"])[0]
                date_from = params.get("from", [""])[0]
                date_to = params.get("to", [""])[0]
                log(f"查询统计摘要: status={status_filter}", "查询")
                summary = get_summary(status_filter, date_from, date_to)
                self._send_json({"status": "ok", "summary": summary})

            elif path == "/api/contracts/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with _contract_sse_lock:
                    _contract_sse_clients.add(self.wfile)
                try:
                    while True:
                        time.sleep(1)
                        with _contract_sse_lock:
                            if self.wfile not in _contract_sse_clients:
                                break
                except:
                    pass
                finally:
                    with _contract_sse_lock:
                        _contract_sse_clients.discard(self.wfile)

            elif path.startswith("/api/contracts/agent-poll"):
                params = parse_qs(parsed.query)
                agent_id = params.get("agent", [""])[0]
                cursor = int(params.get("cursor", [0])[0])
                with _buffer_lock:
                    new_events = _agent_sse_buffer[cursor:]
                    new_cursor = len(_agent_sse_buffer)
                self._send_json({
                    "events": new_events,
                    "cursor": new_cursor,
                    "pending": len(new_events)
                })

            elif path.startswith("/api/contracts/agent-events"):
                params = parse_qs(parsed.query)
                agent_id = params.get("agent", [""])[0]

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                self.wfile.write(f"data: {json.dumps({'type':'connected','agent_id':agent_id}, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()

                with _agent_sse_lock:
                    _agent_sse_clients[self.wfile] = agent_id
                try:
                    self.wfile.write(f"data: {json.dumps({'type':'heartbeat'}, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception as e:
                    pass

                try:
                    while True:
                        time.sleep(3)
                        with _agent_sse_lock:
                            if self.wfile not in _agent_sse_clients:
                                break
                        try:
                            self.wfile.write(f"data: {json.dumps({'type':'heartbeat'}, ensure_ascii=False)}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except:
                            break
                except:
                    pass
                finally:
                    with _agent_sse_lock:
                        _agent_sse_clients.pop(self.wfile, None)

            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:
            log(f"GET请求处理失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            self._send_json({"error": "内部服务器错误"}, 500)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            # 处理产品图片管理 API（无需认证）
            if handle_materials_request and handle_materials_request(self, "POST", path):
                return
            
            # 处理客户无忧 API（无需认证）
            if handle_customers_request and handle_customers_request(self, "POST", path):
                return

            # ========== 产品图片管理 API - POST（无需认证） ==========
            if path.startswith("/api/materials/products/") and "/images/upload" in path:
                self._handle_upload_product_image(path)
                return

            if not (path.startswith("/api/contracts/") or path == "/api/contracts/sync"):
                if not self._check_auth():
                    self._send_json({"error": "unauthorized"}, 401)
                    return

            if path == "/api/contracts/sync":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    
                    # 动态校验产品型号（从知识库获取）
                    products = body.get("products", [])
                    invalid_models = []
                    for prod in products:
                        model = prod.get("model", "").strip()
                        if model and not is_valid_model(model):
                            invalid_models.append(model)
                    
                    if invalid_models:
                        self._send_json({
                            "status": "error",
                            "error": f"无效的产品型号: {', '.join(invalid_models)}",
                            "valid_models": get_all_model_codes()
                        }, 400)
                        return
                    
                    contract = create_contract(body)
                    if contract:
                        self._send_json({"status": "ok", "contract_id": contract.id, "created": True})
                    else:
                        self._send_json({"error": "创建失败"}, 500)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/approve":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract_id = body.get("contract_id", "")
                    approver = body.get("approver", "管理员")
                    if not contract_id:
                        self._send_json({"error": "缺少 contract_id"}, 400)
                        return
                    if approve_contract(contract_id, approver):
                        _notify_sse_clients()
                        self._send_json({"status": "ok", "contract_id": contract_id, "approved": True})
                    else:
                        self._send_json({"error": "合同不存在或审批失败"}, 404)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/reject":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract_id = body.get("contract_id", "")
                    reason = body.get("reason", "")
                    if not contract_id:
                        self._send_json({"error": "缺少 contract_id"}, 400)
                        return
                    if reject_contract(contract_id, reason):
                        _notify_sse_clients()
                        self._send_json({"status": "ok", "contract_id": contract_id, "rejected": True})
                    else:
                        self._send_json({"error": "合同不存在或拒绝失败"}, 404)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/update":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract_id = body.get("contract_id", "")
                    updates = body.get("updates", {})
                    modifier = body.get("modifier", "管理员")
                    if not contract_id:
                        self._send_json({"error": "缺少 contract_id"}, 400)
                        return
                    if not updates:
                        self._send_json({"error": "缺少 updates"}, 400)
                        return
                    contract = update_contract(contract_id, updates, modifier)
                    if contract:
                        _notify_sse_clients()
                        self._send_json({
                            "status": "ok",
                            "contract_id": contract_id,
                            "pdf_path": contract.pdf_path,
                            "updated": True,
                            "needs_reapproval": contract.status == ContractStatus.PENDING
                        })
                    else:
                        self._send_json({"error": "合同不存在或更新失败"}, 404)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/mark-sent":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract_id = body.get("contract_id", "")
                    if mark_sent(contract_id):
                        _notify_sse_clients()
                        self._send_json({"status": "ok", "contract_id": contract_id})
                    else:
                        self._send_json({"error": "合同不存在"}, 404)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/send":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract_id = body.get("contract_id", "")
                    if not contract_id:
                        self._send_json({"error": "缺少 contract_id"}, 400)
                        return
                    if mark_sent(contract_id):
                        _notify_sse_clients()
                        self._send_json({"status": "ok", "contract_id": contract_id, "sent": True})
                    else:
                        self._send_json({"status": "failed", "contract_id": contract_id, "sent": False})
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/cloud-callback":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract_id = body.get("contract_id", "")
                    action = body.get("action", "")
                    if not contract_id or not action:
                        self._send_json({"error": "缺少参数"}, 400)
                        return

                    if action == "approved":
                        if approve_contract(contract_id, "云端"):
                            _notify_sse_clients()
                            self._send_json({"status": "ok", "action": "approved"})
                        else:
                            self._send_json({"error": "审批失败"}, 500)
                    elif action == "rejected":
                        reason = body.get("reason", "")
                        if reject_contract(contract_id, reason):
                            _notify_sse_clients()
                            self._send_json({"status": "ok", "action": "rejected"})
                        else:
                            self._send_json({"error": "拒绝失败"}, 500)
                    elif action == "sent":
                        if mark_sent(contract_id):
                            _notify_sse_clients()
                            self._send_json({"status": "ok", "action": "sent"})
                        else:
                            self._send_json({"error": "标记失败"}, 500)
                    else:
                        self._send_json({"error": "未知操作"}, 400)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            elif path == "/api/contracts/upload-image":
                try:
                    ctype = self.headers.get("Content-Type", "")
                    if "multipart/form-data" not in ctype:
                        self._send_json({"error": "需要 multipart/form-data"}, 400)
                        return
                    content_length = int(self.headers.get("Content-Length", 0))
                    raw_body = self.rfile.read(content_length)
                    boundary = None
                    for part in ctype.split(";"):
                        part = part.strip()
                        if part.startswith("boundary="):
                            boundary = part[len("boundary="):]
                            break
                    if not boundary:
                        self._send_json({"error": "缺少 boundary"}, 400)
                        return

                    from email.parser import BytesParser
                    from email.policy import default as default_policy
                    mime_msg = BytesParser(policy=default_policy).parsebytes(
                        b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + raw_body
                    )
                    file_data = None
                    file_name = None
                    contract_id_part = ""
                    seq_part = ""

                    for part in mime_msg.iter_parts():
                        cd = part.get("Content-Disposition", "")
                        if 'name="image"' in cd:
                            file_data = part.get_content()
                            for seg in cd.split(";"):
                                seg = seg.strip()
                                if seg.startswith("filename="):
                                    file_name = seg[len("filename="):].strip('"')
                        elif 'name="contract_id"' in cd:
                            contract_id_part = part.get_content()
                            if isinstance(contract_id_part, bytes):
                                contract_id_part = contract_id_part.decode("utf-8")
                        elif 'name="seq"' in cd:
                            seq_part = part.get_content()
                            if isinstance(seq_part, bytes):
                                seq_part = seq_part.decode("utf-8")

                    if file_data is None:
                        self._send_json({"error": "缺少图片文件"}, 400)
                        return

                    ext = os.path.splitext(file_name or "")[1] or ".jpg"
                    safe_id = "".join(c for c in (contract_id_part or "upload") if c.isalnum() or c in "-_")
                    seq = int(seq_part) if seq_part and seq_part.isdigit() else 1
                    
                    while True:
                        fname = f"{safe_id}({seq}){ext}"
                        fpath = os.path.join(UPLOADS_DIR, fname)
                        if not os.path.exists(fpath):
                            break
                        seq += 1
                    if isinstance(file_data, str):
                        file_data = file_data.encode("utf-8")
                    with open(fpath, "wb") as f:
                        f.write(file_data)
                    url = f"/api/contracts/image/{quote(fname)}"
                    self._send_json({"status": "ok", "url": url})
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:
            log(f"POST请求处理失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            self._send_json({"error": "内部服务器错误"}, 500)

    def do_DELETE(self):
        """处理 DELETE 请求"""
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            full_path = self.path  # 保留完整路径（包含查询参数）

            # 处理产品图片管理 API（使用完整路径以支持查询参数）
            if handle_materials_request and handle_materials_request(self, "DELETE", full_path):
                return
            
            # 处理客户无忧 API
            if handle_customers_request and handle_customers_request(self, "DELETE", full_path):
                return

            self._send_json({"error": "Method not allowed"}, 405)
        except Exception as e:
            log(f"DELETE请求处理失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            self._send_json({"error": "内部服务器错误"}, 500)

    # ========== 产品图片管理方法 ==========

    def _handle_get_product_images(self, path):
        """获取产品图片列表"""
        try:
            # 解析路径: /api/materials/products/{model}/images
            parts = path.split("/")
            model = parts[4] if len(parts) >= 5 else ""
            model = unquote(model).upper()

            if not model:
                self._send_json({"success": False, "error": "缺少产品型号"}, 400)
                return

            log(f"查询产品图片列表: {model}", "查询")
            product_dir = Path(PRODUCT_IMAGES_DIR) / model
            images = []

            if product_dir.exists():
                for f in sorted(product_dir.iterdir()):
                    if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                        stat = f.stat()
                        images.append({
                            "filename": f.name,
                            "path": str(f),
                            "url": f"/assets/images/{model}/{f.name}",
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        })

            self._send_json({
                "success": True,
                "data": {
                    "model": model,
                    "images": images,
                    "count": len(images)
                }
            })
        except Exception as e:
            log(f"获取图片列表失败: {e}", "ERROR")
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_serve_product_image(self, path):
        """提供产品图片静态文件"""
        try:
            # 解码 URL
            decoded_path = unquote(path)
            relative_path = decoded_path.replace("/assets/images/", "", 1)
            file_path = Path(PRODUCT_IMAGES_DIR) / relative_path

            # 安全检查
            try:
                file_path.relative_to(Path(PRODUCT_IMAGES_DIR))
            except ValueError:
                self.send_response(403)
                self.end_headers()
                return

            if file_path.exists() and file_path.is_file():
                ext = file_path.suffix.lower()
                content_type = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".bmp": "image/bmp",
                    ".webp": "image/webp"
                }.get(ext, "application/octet-stream")

                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            log(f"提供图片失败: {e}", "ERROR")
            self.send_response(500)
            self.end_headers()

    def _handle_upload_product_image(self, path):
        """上传产品图片"""
        try:
            # 解析路径: /api/materials/products/{model}/images/upload
            parts = path.split("/")
            model = parts[4] if len(parts) >= 5 else ""
            model = unquote(model).upper()

            if not model:
                self._send_json({"success": False, "error": "缺少产品型号"}, 400)
                return

            # 解析 multipart/form-data
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._send_json({"success": False, "error": "需要 multipart/form-data"}, 400)
                return

            # 获取 boundary
            boundary = None
            for part in content_type.split(";"):
                if "boundary=" in part:
                    boundary = part.split("boundary=")[1].strip('"')
                    break

            if not boundary:
                self._send_json({"success": False, "error": "无法解析 boundary"}, 400)
                return

            # 读取请求体
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # 解析表单数据
            form_data = self._parse_multipart_form(body, boundary)

            # 获取文件数据
            file_data = form_data.get("image")
            if not file_data:
                self._send_json({"success": False, "error": "缺少图片文件"}, 400)
                return

            filename = form_data.get("filename", "unnamed.jpg")
            description = form_data.get("description", "")

            # 检查文件类型
            allowed_ext = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
            ext = Path(filename).suffix.lower()
            if ext not in allowed_ext:
                self._send_json({"success": False, "error": f"不支持的文件类型: {ext}"}, 400)
                return

            # 创建产品目录
            product_dir = Path(PRODUCT_IMAGES_DIR) / model
            product_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if description:
                safe_desc = "".join(c if c.isalnum() or c in "_-" else "_" for c in description)[:20]
                new_filename = f"{model}_{safe_desc}_{timestamp}{ext}"
            else:
                new_filename = f"{model}_{timestamp}{ext}"

            # 保存文件
            file_path = product_dir / new_filename
            with open(file_path, "wb") as f:
                f.write(file_data if isinstance(file_data, bytes) else file_data.encode())

            self._send_json({
                "success": True,
                "data": {
                    "model": model,
                    "filename": new_filename,
                    "path": str(file_path),
                    "url": f"/assets/images/{model}/{new_filename}",
                    "size": len(file_data) if isinstance(file_data, bytes) else len(file_data.encode())
                },
                "message": "图片上传成功"
            })
        except Exception as e:
            log(f"上传图片失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_delete_product_image(self, path):
        """删除产品图片"""
        try:
            # 解析路径: /api/materials/products/{model}/images/{filename}
            parts = path.split("/")
            if len(parts) < 7:
                self._send_json({"success": False, "error": "路径格式错误"}, 400)
                return

            model = unquote(parts[4]).upper()
            filename = unquote(parts[6])

            if not model or not filename:
                self._send_json({"success": False, "error": "缺少参数"}, 400)
                return

            # 安全检查
            if ".." in filename or "/" in filename or "\\" in filename:
                self._send_json({"success": False, "error": "非法文件名"}, 400)
                return

            file_path = Path(PRODUCT_IMAGES_DIR) / model / filename

            # 检查文件是否存在
            if not file_path.exists():
                self._send_json({"success": False, "error": "文件不存在"}, 404)
                return

            # 移动到回收站
            trash_dir = Path(PRODUCT_IMAGES_DIR) / ".trash" / model
            trash_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_name = f"{file_path.stem}.deleted.{timestamp}{file_path.suffix}"
            trash_path = trash_dir / trash_name

            shutil.move(str(file_path), str(trash_path))

            self._send_json({
                "success": True,
                "data": {
                    "model": model,
                    "filename": filename,
                    "trash_path": str(trash_path)
                },
                "message": "图片已删除"
            })
        except Exception as e:
            log(f"删除图片失败: {e}", "ERROR")
            self._send_json({"success": False, "error": str(e)}, 500)

    def _parse_multipart_form(self, body, boundary):
        """解析 multipart/form-data"""
        result = {}
        boundary_bytes = f"--{boundary}".encode()

        parts = body.split(boundary_bytes)

        for part in parts:
            part = part.strip(b"\r\n")
            if not part or part == b"--":
                continue

            if b"\r\n\r\n" in part:
                headers_bytes, data = part.split(b"\r\n\r\n", 1)
                headers = headers_bytes.decode("utf-8", errors="ignore")

                if "Content-Disposition:" in headers:
                    name = None
                    filename = None

                    for line in headers.split("\r\n"):
                        if "Content-Disposition:" in line:
                            if 'name="' in line:
                                start = line.find('name="') + 6
                                end = line.find('"', start)
                                name = line[start:end]

                            if 'filename="' in line:
                                fstart = line.find('filename="') + 10
                                fend = line.find('"', fstart)
                                filename = line[fstart:fend]

                    if name:
                        if filename:
                            result["filename"] = filename
                            result[name] = data.rstrip(b"\r\n")
                        else:
                            result[name] = data.rstrip(b"\r\n").decode("utf-8", errors="ignore")

        return result

    def _serve_html(self):
        html_path = os.path.join(WEB_DIR, "contracts.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            html = "<h1>合同审批系统</h1><p>页面文件缺失</p>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_favicon(self):
        """提供畅腾LOGO作为favicon"""
        favicon_path = os.path.join(BASE_DIR, "assets", "images", "favicon.ico")
        if os.path.exists(favicon_path):
            self.send_response(200)
            self.send_header("Content-Type", "image/x-icon")
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            with open(favicon_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            # 如果favicon不存在，返回204避免404错误
            self.send_response(204)
            self.end_headers()

    def _serve_customers_html(self):
        """提供客户无忧页面"""
        html_path = os.path.join(WEB_DIR, "customers.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            html = "<h1>客户无忧</h1><p>页面文件缺失</p>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_materials_html(self):
        """提供产品资料页面"""
        html_path = os.path.join(WEB_DIR, "materials.html")
        if os.path.exists(html_path):
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    html = f.read()
            except UnicodeDecodeError:
                # 如果UTF-8失败，尝试用GBK编码读取
                with open(html_path, "r", encoding="gbk") as f:
                    html = f.read()
        else:
            html = "<h1>产品资料</h1><p>页面文件缺失</p>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_js(self):
        js_path = os.path.join(WEB_DIR, "contracts.js")
        if os.path.exists(js_path):
            with open(js_path, "r", encoding="utf-8") as f:
                js = f.read()
            js = js.replace("{{API_TOKEN}}", API_TOKEN or "")
        else:
            js = "// JS文件缺失"

        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(js.encode("utf-8"))

    def log_message(self, format, *args):
        pass

    def handle_error(self):
        import sys
        exc_type = sys.exc_info()[0]
        if exc_type and issubclass(exc_type, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error()


# ========== 启动 ==========

def main():
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    log("═══════════════════════════════════════", "START")
    log("合同审批服务器 v1.0", "START")
    log(f"端口: {SERVER_PORT}", "START")
    log(f"认证: {'已启用' if API_TOKEN else '未启用'}", "START")
    log(f"回调: {CALLBACK_URL or '未配置'}", "START")
    log("产品图片: 已启用", "START")
    log("═══════════════════════════════════════", "START")

    server = ThreadingHTTPServer(("0.0.0.0", SERVER_PORT), ContractHandler)
    log(f"服务器启动 http://0.0.0.0:{SERVER_PORT}", "START")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("服务器正在停止...", "START")
        server.shutdown()
        log("服务器已停止", "START")


if __name__ == "__main__":
    main()
