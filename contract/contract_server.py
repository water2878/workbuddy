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
import hashlib
import shutil
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

# 加载 .env（从项目根目录）
try:
    from dotenv import load_dotenv
    _project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

# ========== 配置 ==========
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))  # 项目根目录
CONTRACTS_DIR = os.path.join(BASE_DIR, "data", "contracts")
PENDING_DIR = os.path.join(CONTRACTS_DIR, "pending")
APPROVED_DIR = os.path.join(CONTRACTS_DIR, "approved")
SENT_DIR = os.path.join(CONTRACTS_DIR, "sent")
TEMPLATE_DIR = os.path.join(BASE_DIR, "contract", "templates")
IMG_DIR = os.path.join(BASE_DIR, "assets", "images")
UPLOADS_DIR = os.path.join(CONTRACTS_DIR, "images")
WEB_DIR = os.path.join(BASE_DIR, "server", "web")

# 确保目录存在
for d in [CONTRACTS_DIR, PENDING_DIR, APPROVED_DIR, SENT_DIR, TEMPLATE_DIR, UPLOADS_DIR]:
    os.makedirs(d, exist_ok=True)

# 服务器配置
SERVER_PORT = int(os.environ.get("CONTRACT_PORT", "5032"))
API_TOKEN = os.environ.get("API_TOKEN", "")  # 为空则不启用认证
CALLBACK_URL = os.environ.get("CALLBACK_URL", "")  # 审批后回调本地助手
CALLBACK_TOKEN = os.environ.get("CALLBACK_TOKEN", "")  # 回调认证

# ========== 数据模型 ==========

class ContractStatus(Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


@dataclass
class OrderInfo:
    customer_name: str = ""
    customer_contact: str = ""
    customer_phone: str = ""
    customer_address: str = ""
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
    """修订记录"""
    at: str = ""
    by: str = ""
    reason: str = ""
    changes: str = ""  # 变更摘要


@dataclass
class Contract:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    status: ContractStatus = ContractStatus.DRAFT
    session_id: str = ""
    customer_wxid: str = ""
    customer_nickname: str = ""
    agent_id: str = ""  # 业务员标识（SALES_ID），用于推送过滤
    order: OrderInfo = field(default_factory=OrderInfo)
    pdf_path: str = ""
    xlsx_path: str = ""
    created_at: str = ""
    approved_at: str = ""
    sent_at: str = ""
    approved_by: str = ""
    reject_reason: str = ""
    revisions: List[Dict[str, str]] = field(default_factory=list)  # 修订记录

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

# 合同缓存
_contracts_cache: Dict[str, Contract] = {}
_contracts_cache_time: float = 0
_contracts_lock = threading.Lock()

def _get_contracts_file() -> str:
    return os.path.join(CONTRACTS_DIR, "contracts.json")


def load_contracts() -> Dict[str, Contract]:
    """加载合同，使用缓存提高性能"""
    global _contracts_cache, _contracts_cache_time
    fpath = _get_contracts_file()
    
    # 检查文件是否存在
    if not os.path.exists(fpath):
        return {}
    
    # 检查文件修改时间，判断是否需要重新加载
    try:
        mtime = os.path.getmtime(fpath)
        with _contracts_lock:
            if mtime <= _contracts_cache_time and _contracts_cache:
                return _contracts_cache
            
            # 文件已修改或缓存为空，重新加载
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
        print(f"[合同] 加载失败: {e}")
        return {}


def save_contracts(contracts: Dict[str, Contract]):
    """保存合同，同时更新缓存"""
    global _contracts_cache, _contracts_cache_time
    fpath = _get_contracts_file()
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in contracts.items()}, f, ensure_ascii=False, indent=2, default=str)
        
        # 更新缓存
        with _contracts_lock:
            _contracts_cache = contracts.copy()
            _contracts_cache_time = os.path.getmtime(fpath)
    except Exception as e:
        print(f"[合同] 保存失败: {e}")


def update_contract_field(contract_id: str, **fields):
    """安全更新单个合同的指定字段（读-改-写原子操作，防止异步线程互相覆盖）"""
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
    """自动字号：根据内容长度和单元格宽度计算"""
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
    """生成订单号: CT + YYYYMMDDHHMMSS"""
    return f"CT{datetime.now().strftime('%Y%m%d%H%M%S')}"


def generate_pdf(contract: Contract) -> tuple:
    """生成合同PDF（COM自动化）"""
    template_xlsx = os.path.join(TEMPLATE_DIR, "精亚国际贸易发展有限公司.xlsx")
    if not os.path.exists(template_xlsx):
        print(f"[合同] 模板不存在: {template_xlsx}")
        return "", ""

    try:
        pdf_path, xlsx_path = _generate_from_xlsx_fill(contract, template_xlsx)
        return pdf_path, xlsx_path
    except Exception as e:
        print(f"[合同] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return "", ""


def _generate_from_xlsx_fill(contract: Contract, template_path: str) -> tuple:
    """基于购买合同.xlsx模板，用Excel COM自动化填充字段并导出PDF
    （与本地 contract_generator.py 完全一致的填充逻辑）

    模板结构（从filled.xlsx xlrd精确提取）：
      Row3:  A=甲方信息，F="乙方："     → F3填客户名
      Row4:  A=联系人，F="联系人："    → F4填联系人
      Row5:  A=电话，F="电话："         → F5填电话
      Row6:  A=地址，F="地址："        → F6填地址
      Row8:  A="下单日期：" F="单号："  → A8填日期, F8填单号
      Row9:  表头(序号/图片/型号/概述/台架尺寸/数量/钢架颜色/价格/单体积/单重量/总价/备注)
      Row10: 单位行(mm/套/元/立方米/KG/元)
      Row11: 第1个产品行（A=序号,C=型号,D=概述,E=台架尺寸,F=数量,G=钢架颜色,H=单价,I=单体积,J=单重量,K=总价）
      Row12: 合计行（B="合计：", C=合计数量, K=合计金额）
      Row13: 备注：
      Row14-20: 条款内容
      Row41+n: "乙方:" / "乙方签名：" / "手机：" / "联系电话：" / "电话/传真："
    """
    order = contract.order
    base_name = f"合同_{order.order_no}_{contract.customer_nickname or '客户'}"
    xlsx_path = os.path.join(PENDING_DIR, base_name + ".xlsx")
    pdf_path = os.path.join(PENDING_DIR, base_name + ".pdf")

    try:
        import win32com.client
        import pythoncom
        import subprocess
        pythoncom.CoInitialize()

        # 清理残留的WPS/Excel COM进程（防止上次残留导致写入失败）
        for proc_name in ["et.exe", "wps.exe", "excel.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc_name],
                             capture_output=True, timeout=5)
            except:
                pass

        # 用DispatchEx强制新建实例（不复用残留的COM对象）
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        wb = excel.Workbooks.Open(os.path.abspath(template_path))
        ws = wb.ActiveSheet

        # ── WPS关键修复：解除工作表保护 ──
        try:
            if ws.ProtectContents or ws.ProtectionMode:
                print(f"  [INFO] 工作表已保护，尝试解除...")
                ws.Unprotect()
                print(f"  [INFO] 解除成功")
            else:
                print(f"  [INFO] 工作表未保护 (ProtectContents={ws.ProtectContents})")
        except Exception as prot_err:
            print(f"  [WARN] 检查/解除保护失败: {prot_err}，尝试强制接触...")
            try:
                # 尝试空密码解除
                ws.Unprotect("")
            except:
                pass

        # 禁用自动计算，防止插入行时触发公式重算导致错误
        excel.Calculation = -4135  # xlCalculationManual

        # ── 安全写入辅助函数（WPS兼容）──
        def _safe_set(cell_ref, value):
            """安全的单元格赋值，WPS兼容"""
            try:
                ws.Range(cell_ref).Value = value
            except Exception as e2:
                print(f"  [WARN] 写入 {cell_ref} 失败: {e2}, 尝试Cells方式")
                try:
                    # 解析 "A11" -> row=11, col=1
                    import re as _re
                    m = _re.match(r'([A-Z]+)(\d+)', str(cell_ref))
                    if m:
                        col_str, row_num = m.group(1), int(m.group(2))
                        col_num = 0
                        for c in col_str:
                            col_num = col_num * 26 + (ord(c) - ord('A') + 1)
                        ws.Cells(row_num, col_num).Value = value
                except Exception as e3:
                    print(f"  [WARN] Cells方式也失败: {e3}")

        date_str = order.order_date or datetime.now().strftime('%Y-%m-%d')

        # ── 填充乙方信息 ──
        _safe_set("F3", f"  乙方：{order.customer_name or contract.customer_nickname or ''}")
        _safe_set("F4", f"  联系人：{order.customer_contact or ''}")
        _safe_set("F5", f"  电话：{order.customer_phone or ''}")
        _safe_set("F6", f"  地址：{order.customer_address or ''}")
        _safe_set("A8", f"  下单日期：{date_str}")
        _safe_set("F8", f"单号：{order.order_no}")

        # ── WPS诊断：写入产品行前测试 ──
        print(f"  [DIAG] 工作表名: {ws.Name}, ProtectContents={ws.ProtectContents}")
        for test_cell in ["Z999", "M11", "A11"]:
            try:
                ws.Range(test_cell).Value = "DIAG"
                v = ws.Range(test_cell).Value
                ws.Range(test_cell).Value = ""
                print(f"  [DIAG] {test_cell} 写入OK")
            except Exception as de:
                print(f"  [DIAG] {test_cell} 写入FAIL: {de}")

        # ── 填充产品行 ──
        products = order.products or []
        total_amount = 0
        total_qty = 0

        insert_count = max(0, len(products) - 1)
        if insert_count > 0:
            try:
                ws.Range(f"11:{10 + insert_count}").Insert(Shift=-4121)  # xlShiftDown
            except Exception as e_ins:
                print(f"  [WARN] 插入行失败: {e_ins}，尝试逐行插入")
                for _ in range(insert_count):
                    try:
                        ws.Rows(11).Insert(Shift=-4121)
                    except:
                        pass

        # 导入标准价格（仅用于价格字段回退，其他字段不再KB回退）
        try:
            from product_kb import extract_product_params, get_standard_price
        except ImportError:
            extract_product_params = None
            get_standard_price = None

        for i, prod in enumerate(products):
            row = 11 + i
            qty = int(prod.get('quantity', 1))
            price = float(prod.get('unit_price', 0))
            if price <= 0 and get_standard_price and prod.get('model'):
                price = get_standard_price(prod.get('model'))
            sub = float(prod.get('subtotal') or price * qty)
            total_amount += sub
            total_qty += qty

            # ── 知识库回退：仅当用户未提供值时用 KB 默认值 ──
            # 关键：回退后的值要写回 prod dict，这样编辑时能保留
            kb_params = {}
            if extract_product_params and prod.get('model'):
                kb_params = extract_product_params(prod.get('model'))

            # 序号（A列）— 用Cells方式避免合并单元格问题
            try:
                ws.Cells(row, 1).Value = i + 1
            except:
                _safe_set(f"A{row}", i + 1)

            # C列 - 型号（必须有值）
            _model_val = prod.get('model', '') or ''
            _safe_set(f"C{row}", _model_val)
            if 'model' not in prod or not prod['model']:
                prod['model'] = _model_val

            # D列 - 概述（空则回退KB）
            _desc = prod.get('description', '')
            if not _desc:
                _desc = kb_params.get('description', '') or '智能升降桌'
            _safe_set(f"D{row}", _desc)
            if not prod.get('description'):
                prod['description'] = _desc

            # E列 - 台架尺寸（空则回退KB）
            _frame_size = prod.get('frame_size', '')
            if not _frame_size:
                _frame_size = kb_params.get('frame_size') or ''
            _safe_set(f"E{row}", _frame_size)
            if not prod.get('frame_size'):
                prod['frame_size'] = _frame_size
            try:
                _auto_font_size(ws.Range(f"E{row}"), min_size=7, default_size=9)
            except:
                pass
            _safe_set(f"F{row}", qty)

            # G列 - 钢架颜色（空则回退KB）
            _frame_color = prod.get('frame_color', '')
            if not _frame_color:
                _frame_color = kb_params.get('color') or ''
            _safe_set(f"G{row}", _frame_color)
            if not prod.get('frame_color'):
                prod['frame_color'] = _frame_color

            if price > 0:
                _safe_set(f"H{row}", price)

            # I列 - 体积（空则回退KB）
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

            # J列 - 单重量（空则回退KB）
            _weight = prod.get('unit_weight', '')
            if not _weight:
                _weight = kb_params.get('weight') or ''
            _safe_set(f"J{row}", _weight)
            if not prod.get('unit_weight'):
                prod['unit_weight'] = _weight

            # K列总价
            _safe_set(f"K{row}", sub)
            # L列备注（无KB回退）
            _remark = prod.get('remark', '')
            _safe_set(f"L{row}", _remark)
            try:
                _auto_font_size(ws.Range(f"L{row}"), min_size=7, default_size=9)
            except:
                pass

            # 设置行高自适应
            try:
                ws.Rows(row).AutoFit()
            except Exception as e_autofit:
                print(f"  [WARN] AutoFit row {row} 失败: {e_autofit}")

            # 设置所有参数列居中
            try:
                data_range = ws.Range(f"A{row}:L{row}")
                data_range.HorizontalAlignment = -4108  # xlCenter
                data_range.VerticalAlignment = -4108    # xlCenter
            except Exception as e_align:
                print(f"  [WARN] 设置居中 row {row} 失败: {e_align}")

            # ── 插入产品图片到B列 ──
            model = prod.get('model', '')
            img_paths = []
            prod_images = prod.get('images', [])
            if prod_images:
                for img_url in prod_images:
                    if img_url.startswith("/contracts/images/"):
                        local_path = os.path.join(CONTRACTS_DIR, "images", img_url.split("/")[-1])
                    elif img_url.startswith("assets/") or img_url.startswith("assets\\"):
                        local_path = os.path.join(BASE_DIR, img_url)
                    elif os.path.isabs(img_url):
                        local_path = img_url
                    else:
                        local_path = os.path.join(BASE_DIR, img_url)
                    if os.path.exists(local_path):
                        img_paths.append(os.path.abspath(local_path))
            if not img_paths and model:
                try:
                    from core.product_service import get_next_image_for_customer
                    img_path, _ = get_next_image_for_customer(model, request_type="smart")
                    if img_path:
                        img_paths.append(img_path)
                except Exception as e:
                    print(f"[合同] 智能选图失败: {e}")
                    # 兜底：直接取第一张
                    img_dir = os.path.join(IMG_DIR, model)
                    if os.path.exists(img_dir):
                        img_files = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
                        if img_files:
                            img_files.sort()
                            img_paths.append(os.path.abspath(os.path.join(img_dir, img_files[0])))
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
                    print(f"[合同] 插入图片失败: {pic_err}")

        # ── 合计行 ──
        total_row = 11 + len(products)
        _safe_set(f"K{total_row}", None)
        try: ws.Cells(total_row, 1).Value = None
        except: pass
        try: ws.Cells(total_row, 1).Value = len(products) + 1
        except: _safe_set(f"A{total_row}", len(products) + 1)
        _safe_set(f"B{total_row}", "合计：")
        _safe_set(f"K{total_row}", float(total_amount))

        # 合计行居中
        try:
            total_range = ws.Range(f"A{total_row}:K{total_row}")
            total_range.HorizontalAlignment = -4108
            total_range.VerticalAlignment = -4108
        except Exception as e_tr:
            print(f"  [WARN] 合计行居中失败: {e_tr}")

        # ── 定金金额 ──
        terms_offset = insert_count
        deposit_row = 15 + terms_offset
        payment_row = 16 + terms_offset
        if total_amount > 0:
            deposit = int(total_amount * 0.45)
            _safe_set(f"B{deposit_row}", (
                f"（1）以上双方签定合同，购方应向供应方支付总货款45%，"
                f"即￥{deposit:,}元整，方可安排发货，收货待定   "
            ))
            if order.payment_terms:
                _safe_set(f"B{payment_row}", f"（2）付款方式：{order.payment_terms}")

        # 恢复自动计算
        excel.Calculation = -4105  # xlCalculationAutomatic

        # ── 乙方签章 ──
        sign_offset = len(products) - 1
        h_brand = 41 + sign_offset
        h_phone = 43 + sign_offset

        name_val = (order.customer_name or contract.customer_nickname or '').replace('\n', ' ').replace('\r', ' ').strip()
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

        # ── 自动调整行高 ──
        try:
            for i in range(len(products)):
                row = 11 + i
                current_h = ws.Rows(row).RowHeight
                ws.Rows(row).RowHeight = max(current_h, 80)
        except Exception as row_err:
            print(f"[合同] 调整行高失败: {row_err}")

        # ── 保存xlsx ──
        wb.SaveAs(os.path.abspath(xlsx_path), FileFormat=51)

        # ── 导出PDF ──
        try:
            wb.ExportAsFixedFormat(0, os.path.abspath(pdf_path))
            print(f"[合同] PDF导出成功: {pdf_path}")
            wb.Close()
            excel.Quit()
            pythoncom.CoUninitialize()
            return pdf_path, xlsx_path
        except Exception as e:
            print(f"[合同] PDF导出失败: {e}，保留xlsx格式")
            wb.Close()
            excel.Quit()
            pythoncom.CoUninitialize()
            return "", xlsx_path

    except ImportError:
        print("[合同] win32com不可用，无法生成合同")
        return "", ""
    except Exception as e:
        print(f"[合同] Excel COM操作失败: {e}")
        import traceback
        traceback.print_exc()
        try:
            excel.Quit()
            pythoncom.CoUninitialize()
        except:
            pass
        return "", ""


# ========== 合同操作 ==========

def _generate_pdf_async(contract_id: str):
    """后台生成PDF（完全非阻塞，不阻塞主进程）"""
    import time
    time.sleep(0.5)  # 短延迟，确保合同记录先保存完成

    def _do_generate():
        try:
            print(f"[PDF] 开始异步生成: {contract_id}", flush=True)
            contracts = load_contracts()
            if contract_id not in contracts:
                print(f"[PDF] 合同已不存在: {contract_id}", flush=True)
                return
            contract = contracts[contract_id]
            
            # 生成PDF（内部会把KB回退值回填到 contract.order.products）
            pdf_path, xlsx_path = generate_pdf(contract)

            if pdf_path and os.path.exists(pdf_path):
                # ── 关键：把KB回填后的产品数据持久化到JSON ──
                # 这样下次编辑时能读到原始值，不会变成空
                contract.pdf_path = pdf_path
                contract.xlsx_path = xlsx_path
                contracts[contract_id] = contract
                save_contracts(contracts)
                print(f"[PDF] 异步生成成功: {contract_id} -> {pdf_path}（含产品数据回填）", flush=True)
            else:
                print(f"[PDF] 异步生成失败（路径为空或文件不存在）: {contract_id}", flush=True)
        except Exception as e:
            print(f"[PDF] 异步生成异常: {contract_id} - {e}", flush=True)
            import traceback
            traceback.print_exc()

    import threading as _th
    t = _th.Thread(target=_do_generate, daemon=True, name=f"pdf-gen-{contract_id}")
    t.start()
    # 不再 join/阻塞！让线程真正在后台跑


def create_contract(order_data: Dict) -> Optional[Contract]:
    """从推送数据创建合同（PDF异步生成）"""
    order = OrderInfo.from_dict(order_data) if isinstance(order_data, dict) else order_data
    if not order.order_no:
        order.order_no = generate_order_no()

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

    # 先保存合同记录，立即通知SSE更新列表（PDF后台异步生成）
    contracts = load_contracts()
    contracts[contract.id] = contract
    save_contracts(contracts)
    _notify_sse_clients()

    # 异步生成PDF
    import threading
    t = threading.Thread(target=_generate_pdf_async, args=(contract.id,), daemon=True)
    t.start()

    return contract


def approve_contract(contract_id: str, approver: str = "管理员") -> bool:
    """审批通过"""
    contracts = load_contracts()
    if contract_id not in contracts:
        return False

    contract = contracts[contract_id]
    contract.status = ContractStatus.APPROVED
    contract.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contract.approved_by = approver

    # 移动PDF
    if contract.pdf_path and os.path.exists(contract.pdf_path):
        new_path = os.path.join(APPROVED_DIR, os.path.basename(contract.pdf_path))
        shutil.move(contract.pdf_path, new_path)
        contract.pdf_path = new_path

    save_contracts(contracts)

    # SSE推送事件给本地助手
    _notify_sse_clients()
    _notify_agent_sse(contract_id, "approved", contract.agent_id, {
        "customer_wxid": contract.customer_wxid,
        "customer_nickname": contract.customer_nickname,
        "pdf_url": f"/api/contracts/pdf/{contract_id}"
    })
    return True


def reject_contract(contract_id: str, reason: str = "") -> bool:
    """拒绝合同"""
    contracts = load_contracts()
    if contract_id not in contracts:
        return False

    contract = contracts[contract_id]
    contract.status = ContractStatus.REJECTED
    contract.reject_reason = reason
    save_contracts(contracts)

    _notify_sse_clients()
    _notify_agent_sse(contract_id, "rejected", contract.agent_id, {
        "reason": reason
    })
    return True


def update_contract(contract_id: str, updates: Dict[str, Any], modifier: str = "管理员") -> Optional[Contract]:
    """更新合同（全状态可编辑，审批后修改需重审）"""
    contracts = load_contracts()
    if contract_id not in contracts:
        return None

    contract = contracts[contract_id]
    old_status = contract.status

    # ── 调试日志：打印收到的更新数据 ──
    print(f"[合同编辑] contract_id={contract_id}, modifier={modifier}", flush=True)
    if "products" in updates:
        for idx, p in enumerate(updates["products"]):
            print(f"[合同编辑]   product[{idx}]: model={p.get('model')}, "
                  f"frame_size='{p.get('frame_size', '')}', "
                  f"frame_color='{p.get('frame_color', '')}', "
                  f"remark='{p.get('remark', '')}', "
                  f"description='{p.get('description', '')[:30]}'", flush=True)

    # 更新字段
    order_dict = asdict(contract.order)
    for key, value in updates.items():
        if key in order_dict:
            order_dict[key] = value
    contract.order = OrderInfo.from_dict(order_dict)

    # 如果已审批/已发送，修改后回退到待审批
    needs_reapproval = old_status in (ContractStatus.APPROVED, ContractStatus.SENT)
    if needs_reapproval:
        contract.status = ContractStatus.PENDING
        contract.approved_at = ""
        contract.approved_by = ""

    # 记录修订
    change_summary = ", ".join(f"{k}=修改" for k in updates.keys() if k != "products")
    if "products" in updates:
        change_summary += ", 产品清单修改"
    contract.revisions = contract.revisions or []
    contract.revisions.append({
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "by": modifier,
        "reason": updates.get("_reason", "编辑修改"),
        "changes": change_summary
    })

    # ⚠️ 先保存编辑数据（即使PDF生成失败也不丢失用户的编辑内容！）
    contracts[contract_id] = contract
    save_contracts(contracts)
    print(f"[合同编辑] 合同数据已保存（PDF生成前），products数量={len(contract.order.products)}", flush=True)

    # 删除旧文件
    for old_path in [contract.pdf_path, contract.xlsx_path]:
        if old_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass

    # 异步重新生成PDF（避免COM操作阻塞HTTP线程）
    print(f"[合同] 编辑后异步生成PDF: {contract_id}", flush=True)
    import threading as _th_edit
    _th_edit.Thread(target=_generate_pdf_async, args=(contract_id,), daemon=True, name=f"pdf-regen-{contract_id}").start()

    return contract


def mark_sent(contract_id: str) -> bool:
    """标记合同已发送（由本地助手回调）"""
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

    save_contracts(contracts)
    return True


# ========== 汇总统计 ==========

def get_summary(status_filter: str = "all", date_from: str = "", date_to: str = "") -> Dict:
    """合同汇总统计"""
    contracts = load_contracts()
    all_contracts = list(contracts.values())

    # 日期筛选
    if date_from:
        all_contracts = [c for c in all_contracts if c.created_at >= date_from]
    if date_to:
        all_contracts = [c for c in all_contracts if c.created_at <= date_to + " 23:59:59"]

    # 状态筛选
    if status_filter != "all":
        all_contracts = [c for c in all_contracts if c.status.value == status_filter]

    # 基础统计
    total_count = len(all_contracts)
    def _safe_subtotal(p):
        s = p.get("subtotal", 0)
        try:
            return float(s) if s else 0
        except (ValueError, TypeError):
            return 0
    total_amount = sum(sum(_safe_subtotal(p) for p in c.order.products) for c in all_contracts)

    # 按状态
    by_status = {}
    for c in all_contracts:
        st = c.status.value
        by_status[st] = by_status.get(st, 0) + 1

    # 按月份
    by_month = {}
    for c in all_contracts:
        month = (c.created_at or "")[:7]  # "2026-04"
        if month:
            if month not in by_month:
                by_month[month] = {"month": month, "count": 0, "amount": 0}
            by_month[month]["count"] += 1
            by_month[month]["amount"] += sum(_safe_subtotal(p) for p in c.order.products)

    # 按客户
    by_customer = {}
    for c in all_contracts:
        name = c.order.customer_name or c.customer_nickname or "未知"
        if name not in by_customer:
            by_customer[name] = {"name": name, "count": 0, "amount": 0, "latest": ""}
        by_customer[name]["count"] += 1
        by_customer[name]["amount"] += sum(_safe_subtotal(p) for p in c.order.products)
        if c.created_at > (by_customer[name]["latest"] or ""):
            by_customer[name]["latest"] = c.created_at

    # 按产品型号
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
    """审批结果回调本地助手"""
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
        print(f"[回调] {action} {contract_id}: {resp.status_code}")
    except Exception as e:
        print(f"[回调] 失败: {e}")


# ========== SSE 推送 ==========

_contract_sse_clients: set = set()
# 面向本地助手的SSE订阅者：{wfile: agent_id}
_agent_sse_clients: Dict = {}
_agent_sse_buffer: List = []  # 全局事件缓冲（轮询兜底）
# 缓冲区大小限制
MAX_BUFFER_SIZE = 1000  # 最多保存1000个事件
# 线程锁
_contract_sse_lock = threading.Lock()
_agent_sse_lock = threading.Lock()
_buffer_lock = threading.Lock()


def _notify_sse_clients():
    """通知审批页面SSE客户端刷新"""
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
    """向本地助手推送审批事件SSE（按agent_id过滤）"""
    payload = {
        "contract_id": contract_id,
        "action": action,
        "agent_id": agent_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        payload.update(extra)

    # 同时写入全局缓冲（供轮询兜底）
    with _buffer_lock:
        _agent_sse_buffer.append(payload)
        # 维护缓冲区大小限制，超过则移除最旧的事件
        if len(_agent_sse_buffer) > MAX_BUFFER_SIZE:
            # 保留最新的MAX_BUFFER_SIZE个事件
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
        """检查API认证"""
        if not API_TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == API_TOKEN
        # 也支持query参数
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        return params.get("access_token", [""])[0] == API_TOKEN

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))

    def _send_file(self, filepath, content_type, filename=None):
        """发送文件"""
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

    # ── GET ──

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.split("?")[0]  # 去掉query string避免?v=xxx干扰路径匹配

            # 合同审批页面（免认证）
            if path == "/" or path == "/contracts":
                self._serve_html()
                return

            # JS文件
            if path == "/contracts.js":
                self._serve_js()
                return

            # 图片文件（免认证）
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

            # 以下API需要认证
            # 合同相关GET免认证（审批页面需要）
            if not (path.startswith("/api/contracts/") or path == "/api/contracts"):
                if not self._check_auth():
                    self._send_json({"error": "unauthorized"}, 401)
                    return

            # 合同列表
            if path == "/api/contracts/list" or path == "/api/contracts/pending":
                params = parse_qs(parsed.query)
                status_filter = params.get("status", ["pending"])[0]
                date_from = params.get("from", [""])[0]
                date_to = params.get("to", [""])[0]
                contracts = load_contracts()

                if status_filter == "all":
                    filtered = list(contracts.values())
                else:
                    filtered = [c for c in contracts.values() if c.status.value == status_filter]

                # 日期筛选
                if date_from:
                    filtered = [c for c in filtered if c.created_at >= date_from]
                if date_to:
                    filtered = [c for c in filtered if c.created_at <= date_to + " 23:59:59"]

                result = []
                for c in filtered:
                    total = sum(p.get("subtotal", 0) for p in c.order.products)
                    products = [f"{p.get('model','')}×{p.get('quantity',1)}" for p in c.order.products]
                    result.append({
                        "id": c.id,
                        "customer": c.customer_nickname or c.order.customer_name or "未知",
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
                        "status": c.status.value,
                        "reject_reason": c.reject_reason,
                        "revisions": c.revisions or [],
                    })

                result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                self._send_json({"status": "ok", "count": len(result), "contracts": result})

            # 合同详情
            elif path.startswith("/api/contracts/detail/"):
                contract_id = path.split("/")[-1]
                contracts = load_contracts()
                if contract_id not in contracts:
                    self._send_json({"error": "合同不存在"}, 404)
                    return
                c = contracts[contract_id]
                self._send_json({"status": "ok", "contract": c.to_dict()})

            # 合同PDF（按需生成 + 缓存）
            elif path.startswith("/api/contracts/pdf/"):
                contract_id = path.split("/")[-1].split("?")[0]
                contracts = load_contracts()
                if contract_id not in contracts:
                    self._send_json({"error": "合同不存在"}, 404)
                    return
                c = contracts[contract_id]

                # PDF不存在或路径无效 → 尝试同步生成一次（按需补生成）
                if not c.pdf_path or not os.path.exists(c.pdf_path):
                    print(f"[PDF] 按需生成: {contract_id} (原路径: {c.pdf_path or '无'})", flush=True)
                    pdf_path, xlsx_path = generate_pdf(c)
                    if pdf_path and os.path.exists(pdf_path):
                        # 安全更新：只改 pdf_path/xlsx_path
                        update_contract_field(contract_id, pdf_path=pdf_path, xlsx_path=xlsx_path)
                        c.pdf_path = pdf_path  # 更新本地变量，下面直接返回文件
                        c.xlsx_path = xlsx_path
                        print(f"[PDF] 按需生成成功: {contract_id} -> {pdf_path}", flush=True)
                    else:
                        # 生成彻底失败才返回错误
                        diag = {
                            "error": "PDF生成失败",
                            "contract_id": contract_id,
                            "pdf_path": c.pdf_path or "(无)",
                            "hint": "WPS COM可能未安装或模板缺失"
                        }
                        self._send_json(diag, 500)
                        return

                self._send_file(c.pdf_path, "application/pdf", os.path.basename(c.pdf_path))

            # 合同汇总
            elif path == "/api/contracts/summary":
                params = parse_qs(parsed.query)
                status_filter = params.get("status", ["all"])[0]
                date_from = params.get("from", [""])[0]
                date_to = params.get("to", [""])[0]
                summary = get_summary(status_filter, date_from, date_to)
                self._send_json({"status": "ok", "summary": summary})

            # SSE 推送
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

            # ── 本地助手轮询接口（SSE兜底，固定5秒内） ──
            elif path.startswith("/api/contracts/agent-poll"):
                params = parse_qs(parsed.query)
                agent_id = params.get("agent", [""])[0]
                cursor = int(params.get("cursor", [0])[0])
                # 从上次游标之后取新事件
                with _buffer_lock:
                    new_events = _agent_sse_buffer[cursor:]
                    new_cursor = len(_agent_sse_buffer)
                self._send_json({
                    "events": new_events,
                    "cursor": new_cursor,
                    "pending": len(new_events)
                })

            # ── 本地助手SSE订阅（按agent_id过滤） ──
            elif path.startswith("/api/contracts/agent-events"):
                params = parse_qs(parsed.query)
                agent_id = params.get("agent", [""])[0]

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                # 发送连接确认
                self.wfile.write(f"data: {json.dumps({'type':'connected','agent_id':agent_id}, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()

                print(f"[DEBUG agent-events] registered agent_id={agent_id}, total_clients={len(_agent_sse_clients)+1}", flush=True)
                with _agent_sse_lock:
                    _agent_sse_clients[self.wfile] = agent_id
                # 发送心跳确认客户端存活
                try:
                    self.wfile.write(f"data: {json.dumps({'type':'heartbeat'}, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    print(f"[DEBUG agent-events] heartbeat sent to client", flush=True)
                except Exception as e:
                    print(f"[DEBUG agent-events] heartbeat failed: {e}", flush=True)

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
            print(f"[ERROR] GET请求处理失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._send_json({"error": "内部服务器错误"}, 500)

    # ── POST ──

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            # 合同相关POST免认证（审批页面操作）
            if not (path.startswith("/api/contracts/") or path == "/api/contracts/sync"):
                if not self._check_auth():
                    self._send_json({"error": "unauthorized"}, 401)
                    return

            # 同步推送（本地→云端）
            if path == "/api/contracts/sync":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    contract = create_contract(body)
                    if contract:
                        self._send_json({"status": "ok", "contract_id": contract.id, "created": True})
                    else:
                        self._send_json({"error": "创建失败"}, 500)
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            # 审批通过
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

            # 拒绝
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

            # 更新合同
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

            # 标记已发送（回调）
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

            # 图片上传
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
                    seq = seq_part or "0"
                    fname = f"{safe_id}({seq}){ext}"
                    fpath = os.path.join(UPLOADS_DIR, fname)
                    if isinstance(file_data, str):
                        file_data = file_data.encode("utf-8")
                    with open(fpath, "wb") as f:
                        f.write(file_data)
                    url = f"/contracts/images/{fname}"
                    self._send_json({"status": "ok", "url": url})
                except Exception as e:
                    self._send_json({"error": str(e)}, 400)

            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:
            print(f"[ERROR] POST请求处理失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._send_json({"error": "内部服务器错误"}, 500)

    # ── 静态文件 ──

    def _serve_html(self):
        """服务审批页面HTML"""
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

    def _serve_js(self):
        """服务审批页面JS"""
        js_path = os.path.join(WEB_DIR, "contracts.js")
        if os.path.exists(js_path):
            with open(js_path, "r", encoding="utf-8") as f:
                js = f.read()
            # 注入API_TOKEN
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
        print(f"[HTTP] {self.client_address[0]} - {format % args}", flush=True)

    def handle_error(self):
        """抑制连接中断等噪音错误"""
        import sys
        exc_type = sys.exc_info()[0]
        if exc_type and issubclass(exc_type, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return  # 浏览器/SSE提前关闭连接，正常现象
        super().handle_error()


# ========== 启动 ==========

def main():
    # 关键：禁用输出缓冲，确保 print 实时显示（不攒缓冲区）
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    print(f"╔══════════════════════════════════════╗", flush=True)
    print(f"║   合同审批服务器 v1.0                ║", flush=True)
    print(f"║   端口: {SERVER_PORT:<28}║", flush=True)
    print(f"║   认证: {'已启用' if API_TOKEN else '未启用':<26}║", flush=True)
    print(f"║   回调: {CALLBACK_URL or '未配置':<26}║", flush=True)
    print(f"╚══════════════════════════════════════╝", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", SERVER_PORT), ContractHandler)
    print(f"[服务器] 启动 http://0.0.0.0:{SERVER_PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[服务器] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
