"""
合同自动生成系统
功能：
1. 从聊天记录提取订单信息
2. 生成合同PDF
3. 审批流程管理
4. 自动发送合同给客户
"""

import os
import json
import re
import uuid
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

# 文件锁，防止并发写入冲突
_contracts_lock = threading.Lock()

# 设置默认 API Key（如果环境变量未设置）
if not os.environ.get("LLM_API_KEY"):
    from dotenv import load_dotenv
    load_dotenv()

# 统一日志函数
try:
    from core.config import log
except ImportError:
    try:
        from config import log
    except ImportError:
        # 兜底日志函数
        def log(text: str, tag: str = "INFO"):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] [{tag}] {text}", flush=True)

# ========== 配置 ==========

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
CONTRACTS_DIR = os.path.join(BASE_DIR, "data", "contracts")
PENDING_DIR = os.path.join(CONTRACTS_DIR, "pending")  # 待审批
APPROVED_DIR = os.path.join(CONTRACTS_DIR, "approved")  # 已通过
SENT_DIR = os.path.join(CONTRACTS_DIR, "sent")  # 已发送
TEMPLATE_DIR = os.path.join(BASE_DIR, "contract", "templates")
IMG_DIR = os.path.join(BASE_DIR, "assets", "images")  # 产品图片目录

# 确保目录存在
for d in [CONTRACTS_DIR, PENDING_DIR, APPROVED_DIR, SENT_DIR, TEMPLATE_DIR]:
    os.makedirs(d, exist_ok=True)


class ContractStatus(Enum):
    DRAFT = "draft"           # 草稿
    PENDING = "pending"       # 待审批
    APPROVED = "approved"     # 已通过
    REJECTED = "rejected"     # 已拒绝
    SENT = "sent"             # 已发送


@dataclass
class OrderInfo:
    """订单信息"""
    # 客户信息
    customer_name: str = ""           # 客户名称/公司名
    customer_contact: str = ""        # 联系人
    customer_phone: str = ""          # 电话
    customer_address: str = ""        # 收货地址

    # 产品信息
    products: List[Dict[str, Any]] = field(default_factory=list)  # [{name, model, quantity, unit_price, subtotal}]
    # 示例: [{"name": "升降桌", "model": "T423", "quantity": 10, "unit_price": 1080, "subtotal": 10800}]

    # 订单信息
    order_no: str = ""                 # 订单号
    order_date: str = ""               # 订单日期
    delivery_date: str = ""           # 交货日期
    payment_terms: str = ""           # 付款方式

    # 电源规格
    voltage: str = "220V/50Hz"        # 电压
    plug_type: str = "国标/欧规/美规"  # 插头类型

    # 其他
    shipping_country: str = ""        # 收货国家
    notes: str = ""                   # 备注

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "OrderInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Contract:
    """合同"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    status: ContractStatus = ContractStatus.DRAFT

    # 关联信息
    session_id: str = ""             # 微信会话ID
    customer_wxid: str = ""          # 客户微信ID
    customer_nickname: str = ""      # 客户昵称

    # 订单信息
    order: OrderInfo = field(default_factory=OrderInfo)

    # 文件路径
    pdf_path: str = ""
    xlsx_path: str = ""

    # 时间戳
    created_at: str = ""
    approved_at: str = ""
    sent_at: str = ""

    # 审批信息
    approved_by: str = ""
    reject_reason: str = ""

    # 修订记录
    revisions: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        data = asdict(self)
        # 确保所有Enum值都被转换为字符串
        data["status"] = self.status.value if isinstance(self.status, ContractStatus) else self.status
        # 处理order中的products，确保无不可序列化对象
        if isinstance(data.get("order"), dict):
            pass  # asdict已处理
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "Contract":
        if isinstance(data.get("status"), str):
            data["status"] = ContractStatus(data["status"])
        if isinstance(data.get("order"), dict):
            data["order"] = OrderInfo.from_dict(data["order"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ========== 合同存储 ==========

def _get_contracts_file() -> str:
    return os.path.join(CONTRACTS_DIR, "contracts.json")


def load_contracts() -> Dict[str, Contract]:
    """加载所有合同（线程安全）"""
    with _contracts_lock:
        fpath = _get_contracts_file()
        if not os.path.exists(fpath):
            return {}

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                data = json.loads(content)
                return {k: Contract.from_dict(v) for k, v in data.items()}
        except (json.JSONDecodeError, IOError) as e:
            log(f"加载合同数据失败: {e}，将重新开始", "合同")
            return {}


def save_contracts(contracts: Dict[str, Contract]):
    """保存所有合同（线程安全）"""
    with _contracts_lock:
        fpath = _get_contracts_file()
        # 使用临时文件写入，然后重命名，避免写入过程中文件损坏
        temp_path = fpath + ".tmp"
        backup_path = fpath + ".bak"
        
        try:
            # 先写入临时文件
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in contracts.items()}, f, ensure_ascii=False, indent=2, default=str)
            
            # Windows: 如果目标文件存在，先备份再删除
            if os.path.exists(fpath):
                try:
                    # 尝试直接删除原文件
                    os.remove(fpath)
                except PermissionError:
                    # 如果删除失败，尝试重命名为备份
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    os.rename(fpath, backup_path)
            
            # 重命名临时文件为目标文件
            os.rename(temp_path, fpath)
            
            # 清理备份文件
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except:
                    pass
                    
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise e


def get_pending_contracts() -> List[Contract]:
    """获取待审批合同"""
    contracts = load_contracts()
    return [c for c in contracts.values() if c.status == ContractStatus.PENDING]


def _get_contract_llm_config():
    """获取合同专用 LLM 配置（优先独立配置，否则回退主 LLM）。
    返回 (api_key, base_url, model)"""
    # 合同专用 LLM（独立 API Key + Base URL）
    contract_api_key = os.environ.get("CONTRACT_LLM_API_KEY", "")
    contract_base_url = os.environ.get("CONTRACT_LLM_BASE_URL", "")
    contract_model = os.environ.get("CONTRACT_LLM_MODEL", "")
    
    if contract_api_key and contract_base_url and contract_model:
        return contract_api_key, contract_base_url, contract_model
    
    # 回退：用主 LLM 配置
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_CONTRACT_MODEL", "")
    return api_key, base_url, model


def check_missing_info(order: 'OrderInfo', chat_history: list = None, skip_llm: bool = False) -> tuple:
    """
    检查合同订单缺少的必要信息
    返回 (缺失信息列表, 订单)
    注：客户信息已在 extract_order_from_chat 中通过 LLM 提取，此处仅做缺失检查
    """
    missing = []

    # 必填字段：联系人、电话、地址、产品型号数量
    if not order.products:
        missing.append("产品型号")
    else:
        for i, prod in enumerate(order.products):
            model_name = prod.get("model", "").strip()
            if not model_name:
                missing.append(f"产品{i+1}型号")
            elif model_name not in _KNOWN_MODELS:
                missing.append(f"产品型号({model_name}不是已知型号)")
            if not prod.get("quantity"):
                missing.append(f"产品{i+1}数量")

    if not order.customer_contact:
        missing.append("联系人")
    if not order.customer_phone:
        missing.append("联系电话")
    if not order.customer_address:
        missing.append("收货地址")

    # 可选字段（不阻塞合同生成）
    # payment_terms 付款方式 - 可选，不强制要求
    # company_name, shipping_country, delivery_date, voltage, plug_type, notes 等

    return missing, order


def generate_info_request_prompt(missing: List[str]) -> str:
    """
    根据缺失信息生成询问客户的消息
    """
    if not missing:
        return None

    # 分类信息
    required = []
    optional = []

    must_have = {"产品型号", "产品1数量", "产品2数量", "产品3数量"}
    for info in missing:
        if info in must_have or "数量" in info:
            required.append(info)
        else:
            optional.append(info)

    parts = []

    # 询问必填信息
    if required:
        # 简化显示
        required_text = "、".join(required)
        parts.append(f"请提供：{required_text}")

    # 询问可选信息
    if optional:
        optional_text = "、".join(optional)
        parts.append(f"（可选：{optional_text}）")

    return "，".join(parts)


# ========== 成交信号检测 ==========

# 强成交信号（高精度匹配）
STRONG_SIGNALS = [
    r"下单", r"确认了", r"成交", r"签合同", r"要合同", r"发合同", r"生成合同",
    r"开发票", r"开票", r"付款", r"转账", r"汇款",
    r"定金", r"扫码", r"支付", r"成交价"
]

# 弱成交信号（需要结合上下文判断）
WEAK_SIGNALS = [
    r"要\s*(\d+)\s*(台|套|个|件)",
    r"(\d+)\s*(台|套|个|件)",
    r"可以", r"行", r"好的", r"没问题"
]

CONFIRM_KEYWORDS = [
    r"(\w+)\s*(\d+)\s*(?:台|套|个|件)",  # "升降桌10台"
    r"(\w+)\s*型号\s*(\w+)",              # "升降桌型号T423"
    r"收货?[地地]址?\s*[:：]?\s*(.+)",     # "收货地址：xxx"
    r"公司\s*名\s*[:：]?\s*(.+)",          # "公司名：xxx"
    r"联系人\s*[:：]?\s*(.+)",             # "联系人：xxx"
    r"电话\s*[:：]?\s*(.+)",               # "电话：xxx"
]




def detect_contract_confirmation(message: str, chat_history: List[Dict] = None) -> bool:
    """
    检测客户对合同询问的确认。
    只有在之前问过"需要合同吗？"之后，客户确认要合同时返回True。
    """
    message_lower = message.lower().strip()

    # 确认模式
    CONFIRM_PATTERNS = [
        r"^要$", r"^要\s*(合同|发)$", r"^是的?$", r"^对$",
        r"要.*合同", r"发.*合同", r"生成.*合同", r"确认.*合同",
        r"^好$", r"^行$", r"^可以$", r"^没问题$",
        r"没问题.*合同", r"好的.*合同",
    ]

    for pattern in CONFIRM_PATTERNS:
        if re.search(pattern, message_lower):
            # 验证上下文：最近消息里有过"需要合同吗？"
            if chat_history and len(chat_history) >= 2:
                recent = chat_history[-3:]  # 看最近3条
                for msg in recent:
                    if "需要合同" in msg.get("content", ""):
                        return True
            # 如果没有上下文，但匹配了强确认词也触发
            if re.search(r"^要$|^是的?$|^好$|^行$|^可以$", message_lower):
                return True

    return False


def detect_closing_signal(message: str, chat_history: List[Dict] = None) -> bool:
    """
    用 AI 分析对话上下文，判断客户是否在明确表达成交意向

    Returns:
        True: AI 判断客户明确要购买或要合同
        False: AI 判断不需要（可能只是询价）
    """
    # 构建完整上下文（历史 + 当前消息）
    full_context = chat_history.copy() if chat_history else []
    full_context.append({'role': 'user', 'content': message})

    # 用 LLM 分析完整上下文
    if full_context:
        return _llm_check_closing(full_context)

    # 无历史且无上下文时，只有关键词才触发
    message_lower = message.lower()

    # 明确要合同/下单的
    if any(k in message_lower for k in ['要合同', '要下单', '签合同', '开发票', '付款', '转账']):
        return True

    # 其他情况默认不需要
    return False


def _strict_check(message: str) -> bool:
    """
    严格模式：弱信号必须满足更多条件才算成交
    """
    # "可以"、"行"、"好的"必须有明确的数量或产品指向
    if re.search(r"可以|行|好的|没问题", message):
        # 如果只是单独的客套话，不算
        if len(message.strip()) < 10 and not re.search(r"\d+", message):
            return False
        return True
    return False


def _llm_check_closing(chat_history: List[Dict]) -> bool:
    """
    用 LLM（Moonshot）分析聊天上下文，判断是否是成交时机

    分析最近5条消息，看是否有明确购买意向
    """
    try:
        import os
        from openai import OpenAI

        api_key, base_url, model = _get_contract_llm_config()

        if not api_key:
            # 回退到 OpenAI
            api_key = os.environ.get("OPENAI_API_KEY", "")
            base_url = "https://api.openai.com/v1"

        if not api_key:
            return False

        # 构建上下文
        recent = chat_history[-5:] if len(chat_history) > 5 else chat_history
        context = "\n".join([
            f"{'客户' if m.get('role') == 'user' else '我'}: {m.get('content', '')[:100]}"
            for m in recent
        ])

        prompt = f"""分析以下对话，只判断最后一条客户消息是否表达了明确的购买成交意向。

对话：
{context}

严格判断标准（只针对最后一条客户消息）：
- 闲聊、问候、询问（如"在吗"、"你好"、"多少钱"、"什么价"）→ 否
- 模糊意向（如"我想来"、"我想看看"、"了解一下"、"考虑下"、"有意向"）→ 否
- 纯信息提供（如"我要10台"但没有明确说要购买/下单/合同）→ 否
- **明确成交信号**：必须同时满足以下条件才回答"是"：
  1. 客户明确说了要购买/下单/签合同/付款
  2. 或客户对报价/方案明确表示确认（如"可以，签合同吧"、"行，下单"、"好的，安排发货"）
  3. 上下文中已有具体产品型号和数量的讨论

常见误判案例（必须回答"否"）：
- "我想来" → 否（只是想来，不是要买）
- "有意向" → 否（只是有兴趣）
- "多少钱" → 否（只是询价）
- "好" → 否（太模糊，需要结合上下文确认是购买确认）
- "可以" → 否（太模糊，可能是"可以告诉我"的意思）

只回答"是"或"否"："""

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=15.0)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0
        )

        result = response.choices[0].message.content.strip()
        return "是" in result

    except Exception:
        return False


# ========== 订单信息提取 ==========

def extract_order_from_chat(chat_history: List[Dict], customer_info: Dict = None) -> OrderInfo:
    """
    从聊天记录提取订单信息（全部由 LLM 一次性提取）

    Args:
        chat_history: 对话历史 [{"role": "user"/"assistant", "content": "..."}]
        customer_info: 客户基本信息 {wxid, nickname, ...}

    Returns:
        OrderInfo对象
    """
    order = OrderInfo()

    # 使用客户画像中的基本信息（如果有）
    if customer_info:
        # 客户昵称可以作为客户名称的默认值
        nickname = customer_info.get('nickname', '')
        if nickname:
            order.customer_name = nickname

    # 构建完整对话文本（取所有角色，客户和AI的信息都可能有用）
    dialog_lines = []
    for msg in chat_history[-20:]:
        content = msg.get("content", "").strip()
        if not content:
            continue
        role = "客户" if msg.get("role") == "user" else "我方"
        dialog_lines.append(f"{role}: {content}")
    user_text = "\n".join(dialog_lines)

    # ── 全部信息：LLM 一次性提取 ──
    if user_text.strip():
        log(f"输入文本长度: {len(user_text)} 字符, 行数: {len(dialog_lines)}", "LLM提取")
        order = _llm_extract_order_info(user_text, order)
    else:
        log(f"输入文本为空，跳过提取", "LLM提取")

    # 生成订单号和日期
    order.order_no = generate_order_no()
    order.order_date = datetime.now().strftime("%Y-%m-%d")
    order.delivery_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    return order


# 已知产品型号（供 LLM prompt 参考）- 动态加载自 product_kb
try:
    from product_kb import get_all_model_codes
    _KNOWN_MODELS = get_all_model_codes()
except ImportError:
    # 兜底：硬编码基本型号
    _KNOWN_MODELS = [
        # 手摇款
        "T724",
        # 单电机款
        "T524", "T523",
        # 双电机款
        "T412", "T423D", "T621",
        # 面板
        "E0", "E1"
    ]


def _llm_extract_order_info(user_text: str, order: 'OrderInfo') -> 'OrderInfo':
    """用 LLM 从用户消息中一次性提取合同所需的全部信息（客户+产品），返回结构化 JSON"""
    try:
        from openai import OpenAI

        api_key, base_url, model = _get_contract_llm_config()

        if not api_key:
            log("[合同] 未配置 LLM_API_KEY，跳过 LLM 信息提取")
            return order

        models_str = "、".join(_KNOWN_MODELS)
        prompt = f"""从以下对话记录中提取合同所需的全部信息。

对话记录：
{user_text}

已知产品型号（仅匹配这些型号，不要编造）：{models_str}

注意："客户"说的话是客户本人的信息，"我方"是销售回复（可能重复客户信息）。

请提取以下信息，如果某个字段在消息中找不到，值留空字符串：

客户信息：
- customer_name: 客户公司/单位名称
- customer_contact: 联系人姓名
- customer_phone: 联系电话/手机号
- customer_address: 收货地址
- shipping_country: 收货国家
- payment_terms: 付款方式
- voltage: 电压规格（如220V/50Hz）
- plug_type: 插头类型（如国标、欧规、美规）
- notes: 备注信息（包含定制需求、颜色要求、特殊配置等）

产品信息（products数组，每个产品含）：
- model: 产品型号（必须是已知型号之一，如果客户说的不是已知型号，选择最接近的标准型号，将定制需求写入notes）
- quantity: 数量（整数，默认1）
- unit_price: 单价（数字，仅当消息中明确提到价格时填写，否则0）

重要规则：
1. 只提取消息中明确提到的信息，不要推测
2. 手机号保持纯数字格式
3. 地址保留完整信息
4. 产品数量必须从消息中提取，不要默认填1
5. 如果消息中提到了价格，填入unit_price；没提到则填0
6. 型号必须严格匹配已知型号列表，不要编造新型号
7. 如果客户要求定制（如特殊颜色、管型、节数等），选择最接近的标准型号填入model，将定制详情写入notes
8. 例如：客户要"F5S定制款红色圆管"，应选择最接近的标准型号（如T621），在notes中注明"定制需求：红色圆管、三节立柱"

只返回 JSON，不要其他文字："""

        model = os.environ.get("LLM_CONTRACT_MODEL", "kimi-k2.5")
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1024,
        )

        result_text = response.choices[0].message.content
        if not result_text:
            log(f"LLM返回为空！model={model}, finish_reason={response.choices[0].finish_reason}", "LLM提取")
            return order
        result_text = result_text.strip()
        log(f"原始返回({len(result_text)}字): {result_text[:500]}", "合同LLM")

        # 解析 JSON（兼容 markdown 代码块包裹）
        json_str = result_text
        if "```" in json_str:
            match = re.search(r'```(?:json)?\s*(.*?)```', json_str, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
            else:
                json_str = result_text

        data = json.loads(json_str)

        # 兼容 LLM 可能返回嵌套结构 {"customer_info": {...}, "products": [...]}
        if "customer_info" in data and isinstance(data["customer_info"], dict):
            flat = data["customer_info"]
            if "products" in data:
                flat["products"] = data["products"]
            data = flat

        # ── 填入客户信息（只覆盖非空值）──
        customer_fields = {
            "customer_name": "customer_name",
            "customer_contact": "customer_contact",
            "customer_phone": "customer_phone",
            "customer_address": "customer_address",
            "shipping_country": "shipping_country",
            "payment_terms": "payment_terms",
            "voltage": "voltage",
            "plug_type": "plug_type",
            "notes": "notes",
        }

        filled = []
        for json_key, order_key in customer_fields.items():
            value = data.get(json_key, "").strip()
            if isinstance(value, str) and value and not getattr(order, order_key, ""):
                setattr(order, order_key, value)
                filled.append(f"{json_key}={value}")

        # ── 填入产品信息 ──
        products_data = data.get("products", [])
        if products_data and isinstance(products_data, list):
            # 尝试获取标准价格
            try:
                from product_kb import get_standard_price
            except ImportError:
                get_standard_price = None

            order.products = []
            for prod in products_data:
                model_name = prod.get("model", "").strip()
                if not model_name:
                    continue
                # 型号必须在已知列表中，否则跳过（不编造型号）
                if model_name not in _KNOWN_MODELS:
                    log(f"型号'{model_name}'不在已知列表中，跳过", "LLM提取")
                    continue
                quantity = int(prod.get("quantity", 1) or 1)
                unit_price = prod.get("unit_price", 0)
                # 如果 LLM 没提价格，尝试从知识库获取标准价格
                if (not unit_price or unit_price == 0) and get_standard_price:
                    unit_price = get_standard_price(model_name)
                order.products.append({
                    "name": "智能升降桌",
                    "model": model_name,
                    "quantity": quantity,
                    "unit_price": float(unit_price) if unit_price else 0,
                    "subtotal": float(unit_price) * quantity if unit_price else 0
                })
                filled.append(f"产品={model_name}x{quantity}")

        if filled:
            log(f"{', '.join(filled)}", "LLM提取")

    except json.JSONDecodeError as e:
        log(f"JSON解析失败: {e}, 原文: {result_text[:200]}", "LLM提取")
    except Exception as e:
        log(f"LLM提取失败: {type(e).__name__}: {e}", "LLM提取")

    return order





def generate_order_no() -> str:
    """生成订单号"""
    now = datetime.now()
    return f"CT{now.strftime('%Y%m%d')}{now.strftime('%H%M%S')[-6:]}"


# ========== 合同生成 ==========

def _auto_font_size(cell, min_size=7, default_size=9):
    """根据单元格宽度和文字长度自动调整字体大小，确保文字不溢出"""
    try:
        text = str(cell.Value) if cell.Value else ""
        if not text or len(text) <= 1:
            cell.Font.Size = default_size
            return
        # 估算：每个字符约需的磅数（中文约7.5，英文约5）
        est_width = sum(7.5 if ord(c) > 127 else 5 for c in text)
        avail_width = cell.Width - 4  # 左右各2磅边距
        if est_width <= avail_width:
            cell.Font.Size = default_size
            return
        ratio = avail_width / est_width
        new_size = max(min_size, int(default_size * ratio))
        cell.Font.Size = new_size
    except Exception:
        pass


def generate_contract(
    order: OrderInfo | Dict[str, Any],
    session_id: str = "",
    customer_wxid: str = "",
    customer_nickname: str = ""
) -> Contract:
    """生成合同"""

    # 支持传入字典，自动转换为OrderInfo
    if isinstance(order, dict):
        order_obj = OrderInfo(
            customer_name=order.get("customer_name", ""),
            customer_contact=order.get("customer_contact", ""),
            customer_phone=order.get("customer_phone", ""),
            customer_address=order.get("customer_address", ""),
            products=order.get("products", []),
            order_no=order.get("order_no", generate_order_no()),
            order_date=order.get("order_date", datetime.now().strftime("%Y-%m-%d")),
            delivery_date=order.get("delivery_date", ""),
            payment_terms=order.get("payment_terms", ""),
            voltage=order.get("voltage", "220V/50Hz"),
            plug_type=order.get("plug_type", "国标/欧规/美规"),
            shipping_country=order.get("shipping_country", ""),
            notes=order.get("notes", ""),
        )
        order = order_obj

    # 确保订单号存在
    if not order.order_no:
        order.order_no = generate_order_no()
    
    # 从notes中解析颜色和面板信息，并添加面板作为独立产品
    _parse_notes_and_add_panel(order)
    
    log(f"创建合同: session_id={session_id}, customer_wxid={customer_wxid}, customer_nickname={customer_nickname}", "生成合同")
    
    contract = Contract(
        id=order.order_no,  # 使用订单号作为合同编号
        session_id=session_id,
        customer_wxid=customer_wxid,
        customer_nickname=customer_nickname,
        order=order,
        status=ContractStatus.PENDING,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    # 生成PDF和xlsx
    pdf_path, xlsx_path = generate_pdf(contract)
    contract.pdf_path = pdf_path
    contract.xlsx_path = xlsx_path  # 保存xlsx路径

    # 保存
    contracts = load_contracts()
    contracts[contract.id] = contract
    save_contracts(contracts)

    # 推送到云端审批服务器
    _push_contract_to_cloud(contract)
    
    # 通知审批人
    _notify_approver(contract)

    return contract


def _parse_notes_and_add_panel(order: OrderInfo) -> None:
    """从notes中解析颜色、面板信息，并添加面板作为独立产品"""
    notes = order.notes or ""
    if not notes:
        return
    
    # 解析颜色（黑色/白色）
    frame_color = ""
    if "黑色" in notes:
        frame_color = "黑色"
    elif "白色" in notes:
        frame_color = "白色"
    
    # 解析面板等级和尺寸
    panel_type = ""  # E0/E1
    panel_size = ""  # 1.4*0.7米等
    
    if "E0" in notes.upper() or "e0" in notes:
        panel_type = "E0级"
    elif "E1" in notes.upper() or "e1" in notes:
        panel_type = "E1级"
    
    # 匹配尺寸格式：1400*700*25mm、1400*700 25mm、1.4*0.7米等
    # 提取长*宽*厚，厚度可选
    size_match = re.search(r'(\d+(?:\.\d+)?)\s*[\*xX]\s*(\d+(?:\.\d+)?)(?:\s*[\*xX\s]\s*(\d+)\s*mm)?', notes)
    if size_match:
        length = float(size_match.group(1))
        width = float(size_match.group(2))
        thickness = size_match.group(3)  # 厚度，可能为None
        
        # 判断单位：如果是小数（如1.4），认为是米，需要转换成毫米
        if length < 100 or width < 100:
            length = int(length * 1000)
            width = int(width * 1000)
        else:
            length = int(length)
            width = int(width)
        
        if thickness:
            panel_size = f"{length}*{width}*{thickness}mm"
        else:
            panel_size = f"{length}*{width}mm"
    
    # 更新现有产品的frame_color
    for prod in order.products:
        if frame_color and not prod.get('frame_color'):
            prod['frame_color'] = frame_color
    
    # 如果有面板信息，添加面板作为独立产品
    if panel_type and panel_size:
        # 获取面板数量（与桌架相同）- 排除面板型号本身
        panel_qty = 0
        for prod in order.products:
            model = prod.get('model', '')
            # 排除面板型号，其他都认为是桌架
            if model and model not in ['E0', 'E1']:
                panel_qty = prod.get('quantity', 1)
                break
        
        if panel_qty > 0:
            # 根据尺寸确定单价（统一使用毫米格式）
            price_map = {
                ("1200", "600"): 90,
                ("1400", "700"): 218,
                ("1600", "800"): 244,
                ("1600", "700"): 244,
                ("1800", "800"): 244,
            }
            unit_price = 0
            # 从 panel_size 提取长和宽（去掉厚度和单位）
            size_parts = panel_size.replace("mm", "").split("*")
            if len(size_parts) >= 2:
                length = size_parts[0]
                width = size_parts[1]
                unit_price = price_map.get((length, width), 0)
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


def _notify_approver(contract: Contract) -> None:
    """通知审批人有新合同待审批"""
    try:
        import sys
        sys.path.insert(0, 'sender')
        sys.path.insert(0, 'core')
        from wechat_sender import send_text_safe
        
        # 从环境变量读取审批人微信昵称
        approver = os.environ.get("APPROVAL_CONTACT", "")
        if not approver:
            log("[合同] 未配置APPROVAL_CONTACT，跳过通知审批人")
            return
        
        order = contract.order
        products_info = []
        for p in order.products:
            model = p.get('model', '')
            qty = p.get('quantity', 0)
            price = p.get('unit_price', 0)
            products_info.append(f"{model} x{qty} ({price}元)")
        
        message = f"""📋 新合同待审批

合同号：{contract.id}
客户：{order.customer_name}
联系人：{order.customer_contact} {order.customer_phone}
金额：{sum(p.get('subtotal', 0) for p in order.products)}元

产品：
{"\n".join(products_info)}

地址：{order.customer_address[:30]}...
交期：{order.delivery_date}

请登录审批系统查看详情。"""
        
        result = send_text_safe(approver, message)
        if result.get('success'):
            log(f"已通知审批人 {approver}", "合同")
        else:
            log(f"通知审批人失败: {result.get('error')}", "合同")

    except Exception as e:
        log(f"通知审批人异常: {e}", "合同")


def _push_contract_to_cloud(contract: Contract) -> None:
    """推送合同数据到云端审批服务器"""
    from dataclasses import asdict

    # 使用统一的 log 函数
    try:
        from core.config import CLOUD_SERVER, CLOUD_TOKEN, SALES_ID, log
    except ImportError:
        try:
            from config import CLOUD_SERVER, CLOUD_TOKEN, SALES_ID, log
        except ImportError as e:
            log(f"[合同] 无法导入配置，跳过云端推送: {e}")
            return

    if not CLOUD_SERVER:
        log("[合同] 未配置云端服务器，跳过推送")
        return

    log(f"[_push_contract_to_cloud] 开始推送合同: {contract.id}")
    log(f"[_push_contract_to_cloud] CLOUD_SERVER={CLOUD_SERVER}")
    log(f"[_push_contract_to_cloud] CLOUD_TOKEN={'已配置' if CLOUD_TOKEN else '未配置'}")
    log(f"[_push_contract_to_cloud] SALES_ID={SALES_ID}")

    try:
        import requests
        order_dict = asdict(contract.order)
        products = order_dict.get('products', [])
        log(f"[_push_contract_to_cloud] 订单数据: {len(order_dict)} 个字段")
        log(f"[_push_contract_to_cloud] 产品数量: {len(products)}")

        payload = {
            **order_dict,
            "session_id": contract.session_id,
            "customer_wxid": contract.customer_wxid,
            "customer_nickname": contract.customer_nickname,
            "agent_id": SALES_ID or "claw",
        }

        log(f"[_push_contract_to_cloud] 准备推送数据到: {CLOUD_SERVER}/api/contracts/sync")
        log(f"[_push_contract_to_cloud] payload大小: {len(str(payload))} 字符")

        headers = {"Content-Type": "application/json"}
        if CLOUD_TOKEN:
            headers["Authorization"] = f"Bearer {CLOUD_TOKEN}"
            log(f"[_push_contract_to_cloud] 使用 Token 认证")

        log(f"[_push_contract_to_cloud] 发送 POST 请求...")
        resp = requests.post(
            f"{CLOUD_SERVER.rstrip('/')}/api/contracts/sync",
            json=payload, headers=headers, timeout=30,
            proxies={"http": None, "https": None}
        )

        log(f"[_push_contract_to_cloud] 收到响应: HTTP {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            log(f"[合同] 已推送到云端: {data.get('contract_id', contract.id)} ({len(products)}个产品)")
        else:
            log(f"[合同] 推送云端失败: HTTP {resp.status_code}")
            log(f"[_push_contract_to_cloud] 响应内容: {resp.text[:500]}")
    except Exception as e:
        log(f"[合同] 推送云端异常: {e}")
        import traceback
        log(f"[_push_contract_to_cloud] 异常详情: {traceback.format_exc()}")


def generate_pdf(contract: Contract) -> tuple:
    """生成合同（COM自动化填充xlsx模板 + 导出PDF）
    
    Returns:
        tuple: (pdf_path, xlsx_path)
    """
    # 尝试用xlsx购买合同模板（COM自动化，保留格式+导出PDF）
    template_xlsx = os.path.join(TEMPLATE_DIR, "精亚国际贸易发展有限公司.xlsx")
    if not os.path.exists(template_xlsx):
        log(f"模板不存在: {template_xlsx}", "合同")
        return "", ""

    try:
        pdf_path, xlsx_path = _generate_from_xlsx_fill(contract, template_xlsx)
        return pdf_path, xlsx_path
    except Exception as e:
        log(f"合同生成失败: {e}", "合同")
        return "", ""


def _generate_from_xlsx_fill(contract: Contract, template_path: str) -> str:
    """基于购买合同.xlsx模板，用Excel COM自动化填充字段并导出PDF

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
        pythoncom.CoInitialize()

        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        # 打开模板
        wb = excel.Workbooks.Open(os.path.abspath(template_path))
        ws = wb.ActiveSheet

        # 禁用自动计算，防止插入行时触发公式重算导致错误
        excel.Calculation = -4135  # xlCalculationManual

        # ── 下单日期和单号（Row 8）──
        date_str = order.order_date or datetime.now().strftime('%Y-%m-%d')

        # ── 填充乙方信息（格式同甲方：两空格前缀，标签+值在同一格）──
        ws.Range("F3").Value = f"  乙方：{order.customer_name or contract.customer_nickname or ''}"
        ws.Range("F4").Value = f"  联系人：{order.customer_contact or ''}"
        ws.Range("F5").Value = f"  电话：{order.customer_phone or ''}"
        ws.Range("F6").Value = f"  地址：{order.customer_address or ''}"
        ws.Range("A8").Value = f"  下单日期：{date_str}"
        ws.Range("F8").Value = f"单号：{order.order_no}"

        # ── 填充产品行 ──
        # 模板布局（xlrd确认）：
        #   Row9=表头(序号/图片/型号/概述/台架尺寸/数量/钢架颜色/价格/单体积/单重量/总价/备注)
        #   Row10=单位行(mm/套/元/立方米/KG/元)，保持不动
        #   Row11=第1个产品行（A11已有"1"序号）
        #   Row12=合计行（B12已有"合计："标签）
        #   Row13=备注
        #   Row14=一.付款方式及条款（标题）
        #   Row15=条款1定金, Row16=条款2付款方式, Row17+=收款银行信息等
        products = order.products or []
        total_amount = 0
        total_qty = 0

        insert_count = max(0, len(products) - 1)
        if insert_count > 0:
            # 在Row11（第1个产品行）前插入n-1行
            # Insert会自动把下面的行（合计、备注、条款等）往下推
            ws.Range(f"11:{10 + insert_count}").Insert(Shift=-4121)  # xlShiftDown

        # 导入产品知识库参数提取函数和标准价格
        extract_product_params = None
        get_standard_price = None
        try:
            # 优先从core目录导入（标准位置）
            import sys
            sys.path.insert(0, os.path.join(BASE_DIR, 'core'))
            from product_kb import extract_product_params, get_standard_price
        except ImportError:
            # 回退：尝试直接从core导入
            try:
                import core.product_kb as product_kb
                extract_product_params = product_kb.extract_product_params
                get_standard_price = product_kb.get_standard_price
            except ImportError:
                pass

        for i, prod in enumerate(products):
            row = 11 + i  # Row11=产品1, Row12=产品2, ...
            qty = int(prod.get('quantity', 1))
            price = float(prod.get('unit_price', 0))
            # 如果没有传入价格，使用标准价格
            if price <= 0 and get_standard_price and prod.get('model'):
                price = get_standard_price(prod.get('model'))
            sub = float(prod.get('subtotal') or price * qty)
            total_amount += sub
            total_qty += qty

            # 从知识库提取参数
            kb_params = {}
            if extract_product_params and prod.get('model'):
                kb_params = extract_product_params(prod.get('model'))

            # 序号（A列）
            ws.Range(f"A{row}").Value = i + 1
            # B列=图片（代码在后面插入图片）
            # C列=型号, D列=概述, E列=台架尺寸, F列=数量, G列=钢架颜色
            # H列=单价, I列=单体积, J列=单重量, K列=总价
            # 优先用产品dict里的值，没有才从知识库取
            
            # 处理面板产品：型号直接显示E0/E1，概述显示"面板"
            model = prod.get('model', '') or ''
            description = prod.get('description', '') or kb_params.get('description', '') or '智能升降桌'
            
            # 如果是面板产品（型号包含E0或E1），调整显示
            if model and ('E0' in model or 'E1' in model):
                # 提取E0或E1作为型号
                if 'E0' in model:
                    model = 'E0'
                elif 'E1' in model:
                    model = 'E1'
                # 概述显示为"面板"
                description = '面板'
            
            ws.Range(f"C{row}").Value = model
            ws.Range(f"D{row}").Value = description
            ws.Range(f"E{row}").Value = prod.get('frame_size', '') or kb_params.get('frame_size', '')  # 台架尺寸
            _auto_font_size(ws.Range(f"E{row}"), min_size=7, default_size=9)   # 台架尺寸自适应字体
            ws.Range(f"F{row}").Value = qty
            ws.Range(f"G{row}").Value = prod.get('frame_color', '') or kb_params.get('color', '')       # 钢架颜色
            if price > 0:
                ws.Range(f"H{row}").Value = price
            
            # I列体积：优先用产品dict，否则从知识库取
            volume_val = prod.get('unit_volume', '')
            if volume_val:
                ws.Range(f"I{row}").Value = volume_val
            else:
                volume_raw = kb_params.get('volume', '')
                vol_match = re.search(r'\(([\d.]+)m³\)', volume_raw)
                if vol_match:
                    ws.Range(f"I{row}").Value = f"{vol_match.group(1)}m³"
                else:
                    ws.Range(f"I{row}").Value = volume_raw
            
            ws.Range(f"J{row}").Value = prod.get('unit_weight', '') or kb_params.get('weight', '')      # 单重量
            ws.Range(f"K{row}").Value = sub
            ws.Range(f"L{row}").Value = prod.get('remark', '')                                               # 备注
            _auto_font_size(ws.Range(f"L{row}"), min_size=7, default_size=9)   # 备注自适应字体

            # 设置行高自适应（让WrapText内容完整显示）
            ws.Rows(row).AutoFit()
            
            # 设置所有参数列居中 (A-L列，水平和垂直居中)
            data_range = ws.Range(f"A{row}:L{row}")
            data_range.HorizontalAlignment = -4108  # xlCenter 水平居中
            data_range.VerticalAlignment = -4108    # xlCenter 垂直居中

            # ── 插入产品图片到B列 ──
            model = prod.get('model', '')
            img_paths = []
            # 优先使用产品自带的images字段（用户上传的图片）
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
            # 如果没有自定义图片，从产品图片目录智能选图
            if not img_paths and model:
                try:
                    from core.product_service import get_next_image_for_customer
                    img_path, _ = get_next_image_for_customer(model, request_type="smart")
                    if img_path:
                        img_paths.append(img_path)
                except Exception as e:
                    log(f"智能选图失败: {e}", "合同")
                    # 兜底：直接取第一张
                    img_dir = os.path.join(IMG_DIR, model)
                    if os.path.exists(img_dir):
                        img_files = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
                        if img_files:
                            img_files.sort()
                            img_paths.append(os.path.abspath(os.path.join(img_dir, img_files[0])))
            if img_paths:
                try:
                    # 图片布局参数
                    COLS = 2          # 每行几列
                    GAP = 4           # 图片间距（磅）
                    PAD = 6           # 单元格内边距（磅）

                    n = len(img_paths)

                    # 先设置B列固定宽度（A4页面安全值），再获取实际可用空间
                    ws.Columns("B").ColumnWidth = 30  # 固定30字符≈A4安全范围
                    cell = ws.Range(f"B{row}")
                    cl = cell.Left
                    ct = cell.Top
                    cw = cell.Width   # 实际可用像素宽度

                    # 根据实际单元格宽度反推每张图最大尺寸
                    avail_w_per_pic = (cw - PAD * 2 - (COLS - 1) * GAP) / COLS
                    target_pic_w = min(avail_w_per_pic, 100)  # 上限100磅
                    target_pic_h = 75                       # 高度上限75磅

                    # 插入并缩放所有图片
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

                    # 计算实际内容总尺寸 → 自适应行高
                    n_rows = max(1, (len(inserted_pics) + COLS - 1) // COLS)
                    content_h = n_rows * (inserted_pics[0][2] if inserted_pics else target_pic_h) + (n_rows - 1) * GAP
                    ws.Rows(row).RowHeight = max(int(content_h) + PAD * 2, 60)
                    ch = ws.Rows(row).RowHeight

                    # 定位：严格在单元格范围内，上下左右居中
                    content_w_actual = sum(pw for _, pw, _ in inserted_pics[:min(n, COLS)]) + (min(n, COLS) - 1) * GAP
                    content_h_actual = n_rows * (inserted_pics[0][2] if inserted_pics else target_pic_h) + (n_rows - 1) * GAP

                    for i, (pic, pw, ph) in enumerate(inserted_pics):
                        c = i % COLS
                        r = i // COLS
                        if n == 1:
                            pic.Left = cl + (cw - pw) / 2
                            pic.Top = ct + (ch - ph) / 2
                        else:
                            # 该行有多少张图
                            row_n = min(n - r * COLS, COLS)
                            row_w = row_n * pw + (row_n - 1) * GAP
                            rx = cl + (cw - row_w) / 2 + c * (pw + GAP)
                            # 垂直整体居中
                            ry = ct + (ch - content_h_actual) / 2 + r * (ph + GAP)
                            pic.Left = max(cl + PAD, rx)  # 不超出左边界
                            pic.Top = ry
                except Exception as pic_err:
                    log(f"插入图片失败: {pic_err}", "合同")

        # ── 合计行（插入后位置 = 11 + len(products)）──
        total_row = 11 + len(products)
        # 只清K列合计金额（模板原有公式），不清F列（合并单元格C:J的一部分，写入会失效）
        ws.Range(f"K{total_row}").Value = None
        # A列序号（合并单元格A:I的一部分，直接写）
        ws.Range(f"A{total_row}").Value = None
        ws.Range(f"A{total_row}").Value = len(products) + 1    # 序号=产品数+1
        ws.Range(f"B{total_row}").Value = "合计："              # 合计标签
        # 注意：C列模板原有公式=K列金额（=K12），不要覆盖！
        # 保持模板公式不变，让K列金额自动填入
        ws.Range(f"K{total_row}").Value = float(total_amount)   # 合计金额

        # 合计行居中 (A-K列)
        total_range = ws.Range(f"A{total_row}:K{total_row}")
        total_range.HorizontalAlignment = -4108  # xlCenter
        total_range.VerticalAlignment = -4108    # xlCenter

        # ── 定金金额（条款1，原始Row15，插入行后偏移到Row15+insert_count）──
        terms_offset = insert_count  # 与插入行数相同
        deposit_row = 15 + terms_offset
        payment_row = 16 + terms_offset
        if total_amount > 0:
            deposit = int(total_amount * 0.45)
            ws.Range(f"B{deposit_row}").Value = (
                f"（1）以上双方签定合同，购方应向供应方支付总货款45%，"
                f"即￥{deposit:,}元整，方可安排发货，收货待定   "
            )
            # 付款方式（条款2）
            if order.payment_terms:
                ws.Range(f"B{payment_row}").Value = f"（2）付款方式：{order.payment_terms}"

        # 恢复自动计算（保存前让Excel重新计算所有公式）
        excel.Calculation = -4105  # xlCalculationAutomatic

        # ── 乙方签章（模板中 H41="乙方:", H42="乙方签名：", H43="手机："）──
        # 标签和值写在同一单元格，格式为"标签\n值"
        # 插入行后标签整体下移：H{41+n-1}="乙方:", H{42+n-1}="乙方签名：", H{43+n-1}="手机："
        sign_offset = len(products) - 1  # 插入行数
        h_brand = 41 + sign_offset   # "乙方:"标签格
        h_sign = 42 + sign_offset    # "乙方签名："标签格
        h_phone = 43 + sign_offset   # "手机："标签格
        h_contact = 44 + sign_offset # "联系电话："标签格
        h_fax = 45 + sign_offset     # "电话/传真："标签格

        # 清理换行符，避免显示异常
        name_val = (order.customer_name or contract.customer_nickname or '').replace('\n', ' ').replace('\r', ' ').strip()
        phone_val = (order.customer_phone or '').replace('\n', ' ').replace('\r', ' ').strip()

        # 读取原标签文本，然后组合"标签 值"写入（保留原标签、追加值，同一行）
        if name_val:
            orig_brand = ws.Range(f"H{h_brand}").Value or ''
            ws.Range(f"H{h_brand}").Value = f"{orig_brand} {name_val}"
        if phone_val:
            orig_phone = ws.Range(f"H{h_phone}").Value or ''
            ws.Range(f"H{h_phone}").Value = f"{orig_phone} {phone_val}"

        # ── 自动调整行高（适配图片高度）──
        try:
            for i in range(len(products)):
                row = 11 + i
                current_h = ws.Rows(row).RowHeight
                ws.Rows(row).RowHeight = max(current_h, 80)  # 至少80磅容纳图片
        except Exception as row_err:
            log(f"调整行高失败: {row_err}", "合同")

        # ── 先保存为xlsx ──
        wb.SaveAs(os.path.abspath(xlsx_path), FileFormat=51)  # 51 = xlsx

        # ── 导出PDF ──
        try:
            wb.ExportAsFixedFormat(0, os.path.abspath(pdf_path))  # 0 = xlTypePDF
            log(f"PDF导出成功: {pdf_path}", "合同")
            wb.Close()
            excel.Quit()
            pythoncom.CoUninitialize()
            return pdf_path, xlsx_path  # 返回(pdf路径, xlsx路径)
        except Exception as e:
            log(f"PDF导出失败: {e}，保留xlsx格式", "合同")
            wb.Close()
            excel.Quit()
            pythoncom.CoUninitialize()
            return "", xlsx_path  # PDF失败时返回空pdf路径 + xlsx路径

    except ImportError:
        log("[合同] win32com不可用，无法生成合同")
        return "", ""
    except Exception as e:
        log(f"Excel COM操作失败: {e}", "合同")
        try:
            excel.Quit()
            pythoncom.CoUninitialize()
        except:
            pass
        return "", ""


def render_contract_html(contract: Contract) -> str:
    """渲染合同HTML"""

    # 计算总价
    total_amount = sum(p.get("subtotal", 0) for p in contract.order.products)

    # 产品表格行
    product_rows = ""
    for i, prod in enumerate(contract.order.products, 1):
        product_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{prod.get('name', '智能升降桌')}</td>
            <td>{prod.get('model', '')}</td>
            <td>{prod.get('quantity', 1)}</td>
            <td>¥{prod.get('unit_price', 0)}</td>
            <td>¥{prod.get('subtotal', 0)}</td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: "SimSun", "宋体", serif;
            font-size: 12pt;
            line-height: 1.8;
            color: #333;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .title {{
            font-size: 24pt;
            font-weight: bold;
            margin-bottom: 20px;
            letter-spacing: 8px;
        }}
        .contract-no {{
            font-size: 10pt;
            color: #666;
        }}
        .section {{
            margin-bottom: 20px;
        }}
        .section-title {{
            font-weight: bold;
            margin-bottom: 10px;
            border-bottom: 1px solid #333;
            padding-bottom: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            border: 1px solid #333;
            padding: 8px 12px;
            text-align: center;
        }}
        th {{
            background: #f5f5f5;
        }}
        .text-left {{
            text-align: left;
        }}
        .text-right {{
            text-align: right;
        }}
        .total-row {{
            font-weight: bold;
            background: #f5f5f5;
        }}
        .signature {{
            margin-top: 50px;
            display: flex;
            justify-content: space-between;
        }}
        .signature-block {{
            width: 45%;
        }}
        .signature-line {{
            margin-top: 60px;
            border-top: 1px solid #333;
            padding-top: 5px;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
        .info-item {{
            display: flex;
        }}
        .info-label {{
            width: 80px;
            font-weight: bold;
        }}
        .info-value {{
            flex: 1;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">购 销 合 同</div>
        <div class="contract-no">合同编号：{contract.order.order_no}</div>
    </div>

    <div class="section">
        <div class="section-title">一、买卖双方信息</div>
        <div class="info-grid">
            <div class="info-item">
                <span class="info-label">甲方（卖方）：</span>
                <span class="info-value">佛山市畅腾智能家居有限公司</span>
            </div>
            <div class="info-item">
                <span class="info-label">乙方（买方）：</span>
                <span class="info-value">{contract.order.customer_name or contract.customer_nickname or '________________'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">联系人：</span>
                <span class="info-value">{contract.order.customer_contact or '________________'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">电话：</span>
                <span class="info-value">{contract.order.customer_phone or '________________'}</span>
            </div>
            <div class="info-item" style="grid-column: span 2;">
                <span class="info-label">地址：</span>
                <span class="info-value">{contract.order.customer_address or '________________'}</span>
            </div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">二、产品信息</div>
        <table>
            <thead>
                <tr>
                    <th>序号</th>
                    <th>产品名称</th>
                    <th>型号</th>
                    <th>数量</th>
                    <th>单价</th>
                    <th>小计</th>
                </tr>
            </thead>
            <tbody>
                {product_rows}
                <tr class="total-row">
                    <td colspan="5" class="text-right">合计金额（大写）：</td>
                    <td>¥{total_amount}</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-title">三、订单信息</div>
        <div class="info-grid">
            <div class="info-item">
                <span class="info-label">订单日期：</span>
                <span class="info-value">{contract.order.order_date}</span>
            </div>
            <div class="info-item">
                <span class="info-label">交货日期：</span>
                <span class="info-value">{contract.order.delivery_date}</span>
            </div>
            <div class="info-item">
                <span class="info-label">收货国家：</span>
                <span class="info-value">{contract.order.shipping_country or '中国'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">电源规格：</span>
                <span class="info-value">{contract.order.voltage} / {contract.order.plug_type}</span>
            </div>
            <div class="info-item" style="grid-column: span 2;">
                <span class="info-label">付款方式：</span>
                <span class="info-value">{contract.order.payment_terms or '预付30%定金，余款发货前结清'}</span>
            </div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">四、备注</div>
        <p>{contract.order.notes or '无'}</p>
    </div>

    <div class="signature">
        <div class="signature-block">
            <div>甲方（盖章）：________________</div>
            <div class="signature-line">佛山市畅腾智能家居有限公司</div>
            <div>日期：________年____月____日</div>
        </div>
        <div class="signature-block">
            <div>乙方（盖章）：________________</div>
            <div class="signature-line">{contract.order.customer_name or contract.customer_nickname or '买方签字盖章'}</div>
            <div>日期：________年____月____日</div>
        </div>
    </div>
</body>
</html>
    """

    return html


# ========== 审批流程 ==========

def approve_contract(contract_id: str) -> bool:
    """审批通过合同"""
    contracts = load_contracts()
    if contract_id not in contracts:
        return False

    contract = contracts[contract_id]
    contract.status = ContractStatus.APPROVED
    contract.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contract.approved_by = "滕成"

    # 移动PDF到已审批目录
    if contract.pdf_path and os.path.exists(contract.pdf_path):
        import shutil
        new_path = os.path.join(APPROVED_DIR, os.path.basename(contract.pdf_path))
        shutil.move(contract.pdf_path, new_path)
        contract.pdf_path = new_path

    # 清理产品中引用的临时上传图片（审批通过，PDF已确定，不再需要临时图片）
    for prod in (contract.order.products or []):
        for img_url in (prod.get('images', []) or []):
            if img_url.startswith("/contracts/images/"):
                img_path = os.path.join(CONTRACTS_DIR, "images", img_url.split("/")[-1])
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass

    save_contracts(contracts)
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
    return True


def update_contract(contract_id: str, updates: Dict[str, Any]) -> Optional[Contract]:
    """更新合同信息并重新生成PDF

    Args:
        contract_id: 合同ID
        updates: 更新字段，支持 OrderInfo 的所有字段及 products 列表

    Returns:
        更新后的 Contract，失败返回 None
    """
    contracts = load_contracts()
    if contract_id not in contracts:
        return None

    contract = contracts[contract_id]

    # 更新 OrderInfo 字段
    order_dict = asdict(contract.order)
    for key, value in updates.items():
        if key in order_dict:
            order_dict[key] = value
    contract.order = OrderInfo.from_dict(order_dict)

    # 删除旧文件
    for old_path in [contract.pdf_path, contract.xlsx_path]:
        if old_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass

    # 重新生成PDF
    pdf_path, xlsx_path = generate_pdf(contract)
    if not pdf_path:
        return None

    contract.pdf_path = pdf_path
    contract.xlsx_path = xlsx_path

    # 保存
    contracts[contract_id] = contract
    save_contracts(contracts)

    return contract


def send_contract(contract_id: str, contracts: Dict[str, 'Contract'] = None) -> bool:
    """发送合同给客户（审批通过后调用）

    通过 wechat_sender 发送PDF合同给客户
    
    Args:
        contract_id: 合同ID
        contracts: 可选，已加载的合同字典。如果提供，将直接使用而不重新加载，
                  且不会调用 save_contracts()，由调用方负责保存
    
    Returns:
        bool: 发送是否成功
    """
    should_save = contracts is None
    if contracts is None:
        contracts = load_contracts()
    
    if contract_id not in contracts:
        return False

    contract = contracts[contract_id]
    if contract.status != ContractStatus.APPROVED:
        return False

    # 用客户昵称/名称搜索并发送
    target = contract.customer_nickname or contract.order.customer_name or contract.session_id
    if not target:
        log(f"发送失败: 找不到客户名称", "合同")
        return False

    if not contract.pdf_path or not os.path.exists(contract.pdf_path):
        log(f"发送失败: PDF文件不存在", "合同")
        return False

    sent = False
    method = ""

    # 通过 wechat_sender 发送
    try:
        from wechat_sender import send_file
        sent = send_file(target, contract.pdf_path)
        method = "wechat_sender"
        # 详细日志由调用方记录，此处仅保留错误日志
    except Exception as e:
        log(f"wechat_sender发送失败: {e}", "合同")

    if sent:
        contract.status = ContractStatus.SENT
        contract.sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 移动PDF到已发送目录
        if contract.pdf_path and os.path.exists(contract.pdf_path):
            import shutil
            new_path = os.path.join(SENT_DIR, os.path.basename(contract.pdf_path))
            shutil.move(contract.pdf_path, new_path)
            contract.pdf_path = new_path

        # 只有在自己加载合同的情况下才保存
        if should_save:
            save_contracts(contracts)
        # 日志已由调用方记录，此处不再重复

    return sent


# ========== 命令行管理 ==========

def print_pending_contracts():
    """打印待审批合同列表"""
    pending = get_pending_contracts()
    if not pending:
        log("没有待审批的合同")
        return

    log(f"{'='*60}")
    log(f"待审批合同 ({len(pending)}份)")
    log(f"{'='*60}")
    for c in pending:
        total = sum(p.get("subtotal", 0) for p in c.order.products)
        products = ", ".join([f"{p['model']}×{p.get('quantity', 1)}" for p in c.order.products])
        log(f"[{c.id}] {c.customer_nickname or '客户'}")
        log(f"  订单号: {c.order.order_no}")
        log(f"  产品: {products or '未指定'}")
        log(f"  金额: ¥{total}")
        log(f"  创建: {c.created_at}")
        log(f"  PDF: {c.pdf_path}")
    log(f"{'='*60}")


def main():
    """命令行入口"""
    import sys

    if len(sys.argv) < 2:
        log("用法: python contract_generator.py <命令> [参数]")
        log("命令:")
        log("  list              - 查看待审批合同")
        log("  approve <合同ID>  - 审批通过")
        log("  reject <合同ID>    - 拒绝合同")
        log("  send <合同ID>      - 发送合同给客户")
        return

    cmd = sys.argv[1]

    if cmd == "list":
        print_pending_contracts()

    elif cmd == "approve":
        if len(sys.argv) < 3:
            log("请提供合同ID")
            return
        contract_id = sys.argv[2]
        if approve_contract(contract_id):
            log(f"合同 {contract_id} 已审批通过")
        else:
            log(f"合同 {contract_id} 不存在")

    elif cmd == "reject":
        if len(sys.argv) < 3:
            log("请提供合同ID")
            return
        contract_id = sys.argv[2]
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        if reject_contract(contract_id, reason):
            log(f"合同 {contract_id} 已拒绝")
        else:
            log(f"合同 {contract_id} 不存在")

    elif cmd == "send":
        if len(sys.argv) < 3:
            log("请提供合同ID")
            return
        contract_id = sys.argv[2]
        if send_contract(contract_id):
            log(f"合同 {contract_id} 已发送给客户")
        else:
            log(f"合同 {contract_id} 不存在或未审批")


if __name__ == "__main__":
    main()
