"""
客户画像同步到客户无忧系统
支持审批流程，审批通过后自动推送
"""
import os
import json
import requests
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum

# 从 config 导入配置（config 已加载 .env）
from config import KEHU51_API_URL, log, os as config_os

# 客户无忧 API Key
KEHU51_API_KEY = config_os.environ.get("KEHU51_API_KEY", "")

# 数据目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOMER_SYNC_DIR = os.path.join(BASE_DIR, "data", "customer_sync")
os.makedirs(CUSTOMER_SYNC_DIR, exist_ok=True)

PENDING_FILE = os.path.join(CUSTOMER_SYNC_DIR, "pending.json")
APPROVED_FILE = os.path.join(CUSTOMER_SYNC_DIR, "approved.json")
SENT_FILE = os.path.join(CUSTOMER_SYNC_DIR, "sent.json")


class SyncStatus(Enum):
    PENDING = "pending"      # 待审批
    APPROVED = "approved"    # 已审批
    SENT = "sent"           # 已推送
    REJECTED = "rejected"    # 已拒绝
    FAILED = "failed"       # 推送失败


@dataclass
class CustomerSyncRecord:
    """客户同步记录"""
    id: str                          # 记录ID
    customer_id: str                 # 客户微信ID
    customer_nickname: str           # 客户昵称
    status: str                      # 状态
    
    # 客户无忧字段
    cus_name: str = ""              # 客户名称
    mobile_phone: str = ""          # 手机号
    work_name: str = ""             # 工作单位
    work_address: str = ""          # 公司地址
    email: str = ""                 # 邮箱
    cus_intro: str = ""             # 客户介绍
    get_time: str = ""              # 获得时间
    industry: str = ""              # 行业
    source: str = ""                # 客户来源
    
    # 业务员信息（用于区分不同业务员的数据）
    agent_id: str = ""              # 业务员ID
    sales_id: str = ""              # 销售员ID（兼容字段）
    
    # 原始画像数据
    original_profile: Dict = field(default_factory=dict)
    
    # 审批信息
    created_at: str = ""
    approved_at: str = ""
    sent_at: str = ""
    approved_by: str = ""
    reject_reason: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CustomerSyncRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _load_json(filepath: str, default=None):
    """加载JSON文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _save_json(filepath: str, data):
    """保存JSON文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_pending_records() -> Dict[str, Dict]:
    """加载待审批记录"""
    return _load_json(PENDING_FILE, {})


def load_approved_records() -> Dict[str, Dict]:
    """加载已审批记录"""
    return _load_json(APPROVED_FILE, {})


def load_sent_records() -> Dict[str, Dict]:
    """加载已推送记录"""
    return _load_json(SENT_FILE, {})


def save_pending_records(records: Dict[str, Dict]):
    """保存待审批记录"""
    _save_json(PENDING_FILE, records)


def save_approved_records(records: Dict[str, Dict]):
    """保存已审批记录"""
    _save_json(APPROVED_FILE, records)


def save_sent_records(records: Dict[str, Dict]):
    """保存已推送记录"""
    _save_json(SENT_FILE, records)


def profile_to_kehu51_data(profile: Dict, customer_nickname: str) -> Dict:
    """将客户画像转换为客户无忧API格式"""
    profile_data = profile.get("profile", {})
    
    data = {
        "GetTime": profile.get("first_contact", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "CusName": _get_field_value(profile_data, "customer_name") or profile.get("nickname", customer_nickname)[:50],
        "sex": "",
        "CityID": "",
        "WorkAddress": _get_field_value(profile_data, "address")[:200],
        "MobilePhone": _get_field_value(profile_data, "phone")[:20],
        "Email": _get_field_value(profile_data, "email")[:100],
        "ClassID": ",".join(profile.get("tags", []))[:50] if profile.get("tags") else "",
        "StateID": "",
        "LevelID": profile.get("priority", "")[:20],
        "SourceID": _get_field_value(profile_data, "demand_type")[:50],
        "MaturityID": "",
        "WorkName": _get_field_value(profile_data, "customer_name")[:100],
        "IndustryID": _get_field_value(profile_data, "industry")[:50],
        "WorkPhone": "",
        "CusIntro": profile.get("notes", "")[:500],
        "Customize1": "",
        "Customize2": "",
        "WorkSite": "",
        "CustomizeClass1": "",
        "CustomizeClass2": "",
        "custom_date_6": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Birthday": "",
        "QQ": "",
        "MSN": "",
        "IDNumber": "",
        "Src2": "微信",
        "Src2FromID": profile.get("customer_id", ""),
        "AdvertiserID": ""
    }
    return data


def create_sync_record(customer_id: str, customer_nickname: str, profile: Dict, agent_id: str = "") -> CustomerSyncRecord:
    """创建同步记录"""
    record_id = f"CUST{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # 提取关键信息（支持 {value, source, confidence} 结构）
    profile_data = profile.get("profile", {})
    
    # 从配置获取当前业务员ID
    if not agent_id:
        from config import SALES_ID
        agent_id = SALES_ID or "default"
    
    record = CustomerSyncRecord(
        id=record_id,
        customer_id=customer_id,
        customer_nickname=customer_nickname,
        status=SyncStatus.PENDING.value,
        
        # 客户无忧字段
        cus_name=_get_field_value(profile_data, "customer_name") or customer_nickname,
        mobile_phone=_get_field_value(profile_data, "phone"),
        work_name=_get_field_value(profile_data, "customer_name"),
        work_address=_get_field_value(profile_data, "address"),
        email=_get_field_value(profile_data, "email"),
        cus_intro=profile.get("notes", ""),
        get_time=profile.get("first_contact", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        industry=_get_field_value(profile_data, "industry"),
        source=_get_field_value(profile_data, "demand_type") or "微信",
        
        # 业务员信息
        agent_id=agent_id,
        sales_id=agent_id,
        
        # 原始数据
        original_profile=profile,
        
        # 时间戳
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    
    # 保存到待审批
    pending = load_pending_records()
    pending[record_id] = record.to_dict()
    save_pending_records(pending)
    
    return record


def approve_record(record_id: str, approved_by: str = "") -> bool:
    """审批通过记录"""
    pending = load_pending_records()
    
    if record_id not in pending:
        return False
    
    record_data = pending.pop(record_id)
    record_data["status"] = SyncStatus.APPROVED.value
    record_data["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record_data["approved_by"] = approved_by
    
    # 移动到已审批
    approved = load_approved_records()
    approved[record_id] = record_data
    
    save_pending_records(pending)
    save_approved_records(approved)
    
    return True


def reject_record(record_id: str, reason: str = "") -> bool:
    """拒绝记录"""
    pending = load_pending_records()
    
    if record_id not in pending:
        return False
    
    record_data = pending.pop(record_id)
    record_data["status"] = SyncStatus.REJECTED.value
    record_data["reject_reason"] = reason
    
    save_pending_records(pending)
    
    # 保存到拒绝记录（可选）
    rejected_file = os.path.join(CUSTOMER_SYNC_DIR, "rejected.json")
    rejected = _load_json(rejected_file, {})
    rejected[record_id] = record_data
    _save_json(rejected_file, rejected)
    
    return True


def delete_record(record_id: str) -> bool:
    """删除记录（从待审批或已审批列表中删除，删除后可重新推送）"""
    # 尝试从待审批列表删除
    pending = load_pending_records()
    if record_id in pending:
        record_data = pending.pop(record_id)
        save_pending_records(pending)
        log(f"[DELETE] Record {record_id} deleted from pending")
        return True
    
    # 尝试从已审批列表删除
    approved = load_approved_records()
    if record_id in approved:
        record_data = approved.pop(record_id)
        save_approved_records(approved)
        log(f"[DELETE] Record {record_id} deleted from approved")
        return True
    
    return False


def push_to_cloud_approval(record_id: str, cloud_server: str = "http://120.26.84.224:5032") -> Dict:
    """推送记录到云端客户无忧审批系统"""
    approved = load_approved_records()
    
    if record_id not in approved:
        return {"success": False, "error": "记录不存在或未审批"}
    
    record_data = approved[record_id]
    
    # 准备推送到云端审批系统的数据
    api_data = {
        "id": record_data.get("id", ""),
        "customer_id": record_data.get("customer_id", ""),
        "customer_nickname": record_data.get("customer_nickname", ""),
        "status": "pending",  # 推送到云端后状态为待审批
        "cus_name": record_data.get("cus_name", ""),
        "mobile_phone": record_data.get("mobile_phone", ""),
        "work_name": record_data.get("work_name", ""),
        "work_address": record_data.get("work_address", ""),
        "email": record_data.get("email", ""),
        "cus_intro": record_data.get("cus_intro", ""),
        "get_time": record_data.get("get_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "industry": record_data.get("industry", ""),
        "source": record_data.get("source", "微信"),
        "agent_id": record_data.get("agent_id", ""),
        "sales_id": record_data.get("sales_id", ""),
    }
    
    try:
        # 推送到云端审批系统
        url = f"{cloud_server}/api/customers/sync"
        headers = {"Content-Type": "application/json"}
        
        log(f"[CLOUD PUSH] 推送客户 {record_data.get('cus_name')} 到云端审批系统")
        
        resp = requests.post(
            url,
            json=api_data,
            headers=headers,
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            
            if result.get("success"):
                # 标记为已推送到云端
                record_data["status"] = SyncStatus.SENT.value
                record_data["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                record_data["cloud_synced"] = True
                record_data["cloud_record_id"] = result.get("data", {}).get("id", "")
                
                # 移动到已推送
                sent = load_sent_records()
                sent[record_id] = record_data
                save_sent_records(sent)
                
                # 从已审批中移除
                del approved[record_id]
                save_approved_records(approved)
                
                log(f"[CLOUD PUSH] 成功: {record_data.get('cus_name')}")
                return {"success": True, "result": result}
            else:
                error_msg = result.get("error", "未知错误")
                log(f"[CLOUD PUSH] 失败: {error_msg}")
                return {"success": False, "error": error_msg}
        else:
            error_msg = f"HTTP {resp.status_code}: {resp.text}"
            log(f"[CLOUD PUSH] 失败: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        log(f"[CLOUD PUSH] 异常: {e}")
        return {"success": False, "error": str(e)}


def push_to_kehu51(record_id: str) -> Dict:
    """推送记录到客户无忧"""
    approved = load_approved_records()
    
    if record_id not in approved:
        return {"success": False, "error": "记录不存在或未审批"}
    
    record_data = approved[record_id]
    
    # 准备API数据
    api_data = {
        "GetTime": record_data.get("get_time", ""),
        "CusName": record_data.get("cus_name", ""),
        "MobilePhone": record_data.get("mobile_phone", ""),
        "WorkName": record_data.get("work_name", ""),
        "WorkAddress": record_data.get("work_address", ""),
        "Email": record_data.get("email", ""),
        "CusIntro": record_data.get("cus_intro", ""),
        "IndustryID": record_data.get("industry", ""),
        "SourceID": record_data.get("source", "微信"),
        "Src2": "微信",
        "Src2FromID": record_data.get("customer_id", ""),
    }
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEHU51_API_KEY}" if KEHU51_API_KEY else ""
        }
        
        resp = requests.post(
            KEHU51_API_URL,
            json=api_data,
            headers=headers,
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            
            # 标记为已推送
            record_data["status"] = SyncStatus.SENT.value
            record_data["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 移动到已推送
            sent = load_sent_records()
            sent[record_id] = record_data
            save_sent_records(sent)
            
            # 从已审批中移除
            del approved[record_id]
            save_approved_records(approved)
            
            return {"success": True, "result": result}
        else:
            record_data["status"] = SyncStatus.FAILED.value
            record_data["error"] = f"HTTP {resp.status_code}: {resp.text}"
            save_approved_records(approved)
            
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
            
    except Exception as e:
        record_data["status"] = SyncStatus.FAILED.value
        record_data["error"] = str(e)
        save_approved_records(approved)
        
        return {"success": False, "error": str(e)}


def get_pending_list() -> List[Dict]:
    """获取待审批列表"""
    pending = load_pending_records()
    return list(pending.values())


def get_approved_list() -> List[Dict]:
    """获取已审批列表"""
    approved = load_approved_records()
    return list(approved.values())


def get_sent_list() -> List[Dict]:
    """获取已推送列表"""
    sent = load_sent_records()
    return list(sent.values())


def get_record(record_id: str) -> Optional[Dict]:
    """获取单条记录"""
    # 依次查找
    for filepath in [PENDING_FILE, APPROVED_FILE, SENT_FILE]:
        data = _load_json(filepath, {})
        if record_id in data:
            return data[record_id]
    return None


def update_record(record_id: str, updates: Dict) -> bool:
    """更新记录信息（审批前可编辑）"""
    pending = load_pending_records()
    
    if record_id not in pending:
        return False
    
    record = pending[record_id]
    record.update(updates)
    
    save_pending_records(pending)
    return True


def is_customer_synced(customer_id: str) -> bool:
    """检查客户是否已经推送过（避免重复推送）"""
    # 检查已推送列表
    sent = load_sent_records()
    for record in sent.values():
        if record.get("customer_id") == customer_id:
            return True
    return False


def get_synced_customer_ids() -> set:
    """获取所有已推送的客户ID集合（合并多个来源）"""
    synced_ids = set()
    
    # 从 sent_records 获取
    sent = load_sent_records()
    synced_ids.update({record.get("customer_id") for record in sent.values() if record.get("customer_id")})
    
    # 从 synced_customers.json 获取
    synced_ids.update(_get_synced_customer_ids_from_file())
    
    return synced_ids


def _mark_customer_as_synced(customer_id: str, cloud_id: str = ""):
    """标记客户为已推送状态（用于去重）"""
    try:
        synced_file = os.path.join(CUSTOMER_SYNC_DIR, "synced_customers.json")
        synced = _load_json(synced_file, {})
        
        synced[customer_id] = {
            "customer_id": customer_id,
            "cloud_id": cloud_id,
            "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        _save_json(synced_file, synced)
        log(f"[SYNC] 客户 {customer_id} 已标记为已推送")
    except Exception as e:
        log(f"[ERROR] 标记客户已推送状态失败: {e}")


def check_customer_exists_in_cloud(customer_id: str, cloud_server: str = None) -> bool:
    """查询云端是否存在该客户
    
    Returns:
        bool: True 表示云端存在，False 表示云端不存在或查询失败
    """
    try:
        if cloud_server is None:
            cloud_server = CLOUD_APPROVAL_SERVER
        url = f"{cloud_server}/api/customers/check"
        headers = {"Content-Type": "application/json"}
        
        resp = requests.post(
            url,
            json={"customer_id": customer_id},
            headers=headers,
            timeout=30  # 增加超时时间到30秒
        )
        
        if resp.status_code == 200:
            result = resp.json()
            exists = result.get("data", {}).get("exists", False)
            log(f"[CLOUD CHECK] 客户 {customer_id} 云端存在: {exists}")
            return exists
        else:
            log(f"[CLOUD CHECK] 查询客户存在状态失败: HTTP {resp.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        log(f"[CLOUD CHECK] 查询客户存在状态超时: {customer_id}")
        return False
    except Exception as e:
        log(f"[CLOUD CHECK] 查询客户存在状态异常: {e}")
        return False


def _get_synced_customer_ids_from_file() -> set:
    """从同步记录文件获取已推送客户ID"""
    try:
        synced_file = os.path.join(CUSTOMER_SYNC_DIR, "synced_customers.json")
        synced = _load_json(synced_file, {})
        return set(synced.keys())
    except Exception as e:
        log(f"[ERROR] 读取已推送客户记录失败: {e}")
        return set()


def _get_field_value(profile_data: Dict, field: str) -> str:
    """获取字段值，支持 {value, source, confidence} 结构和直接值"""
    field_data = profile_data.get(field, "")
    if isinstance(field_data, dict):
        return field_data.get("value", "")
    return str(field_data) if field_data else ""


def is_profile_complete(profile: Dict) -> bool:
    """检查客户画像数据是否完整（必须有手机号和公司名/联系人）"""
    profile_data = profile.get("profile", {})
    
    # 检查必要字段（支持 {value, source, confidence} 结构）
    phone = _get_field_value(profile_data, "phone")
    customer_name = _get_field_value(profile_data, "customer_name")
    
    has_phone = bool(phone)  # 手机号必要
    has_company = bool(customer_name)  # 公司名/联系人必要
    
    # 必须有手机号和公司名
    if has_phone and has_company:
        return True
    
    return False


def get_profile_completeness(profile: Dict) -> Dict:
    """获取客户画像完整度信息"""
    profile_data = profile.get("profile", {})
    
    return {
        "has_phone": bool(_get_field_value(profile_data, "phone")),  # 必要
        "has_company": bool(_get_field_value(profile_data, "customer_name")),  # 必要
        "has_name": bool(profile.get("nickname") or _get_field_value(profile_data, "customer_name")),
        "has_email": bool(_get_field_value(profile_data, "email")),  # 可选
        "has_address": bool(_get_field_value(profile_data, "address")),  # 可选
        "has_industry": bool(_get_field_value(profile_data, "industry")),  # 可选
    }


def is_customer_in_queue(customer_id: str) -> bool:
    """检查客户是否已在待审批或已审批队列中"""
    # 检查待审批列表
    pending = load_pending_records()
    for record in pending.values():
        if record.get("customer_id") == customer_id:
            return True
    
    # 检查已审批列表
    approved = load_approved_records()
    for record in approved.values():
        if record.get("customer_id") == customer_id:
            return True
    
    return False


def sync_profile_if_not_exists(customer_id: str, customer_nickname: str, profile: Dict) -> Optional[CustomerSyncRecord]:
    """如果客户未推送过、不在队列中且数据完整，则创建同步记录
    
    Returns:
        CustomerSyncRecord: 新创建的记录，如果已推送、在队列中或数据不完整则返回 None
    """
    # 1. 检查是否已经推送过（已推送的不重复处理）
    if is_customer_synced(customer_id):
        log(f"[SYNC] Customer {customer_id} already synced, skipping")
        return None
    
    # 2. 检查是否已在队列中（待审批或已审批）
    if is_customer_in_queue(customer_id):
        log(f"[SYNC] Customer {customer_id} already in queue (pending or approved), skipping")
        return None
    
    # 3. 检查数据是否完整
    if not is_profile_complete(profile):
        completeness = get_profile_completeness(profile)
        missing = [k for k, v in completeness.items() if not v]
        log(f"[SYNC] Customer {customer_id} profile incomplete, skipping. Missing: {missing}")
        return None
    
    # 4. 创建新记录
    return create_sync_record(customer_id, customer_nickname, profile)


# ==================== 推送本地客户画像到云端审批系统 ====================

CLOUD_APPROVAL_SERVER = "http://120.26.84.224:5032"


def load_local_customer_profiles() -> List[Dict]:
    """加载本地所有客户画像数据"""
    profiles = []
    chat_history_dir = os.path.join(BASE_DIR, "data", "chat_history")
    
    if not os.path.exists(chat_history_dir):
        return profiles
    
    for filename in os.listdir(chat_history_dir):
        if filename.endswith("_profile.json") and filename != "customer_profile_template.json":
            filepath = os.path.join(chat_history_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                    profile["_source_file"] = filename
                    profiles.append(profile)
            except Exception as e:
                log(f"[ERROR] 加载客户画像失败 {filename}: {e}")
    
    return profiles


def profile_to_cloud_format(profile: Dict) -> Dict:
    """将本地客户画像转换为云端审批系统格式"""
    profile_data = profile.get("profile", {})
    
    # 提取字段值（支持 {value, source, confidence} 结构）
    def get_value(field_data):
        if isinstance(field_data, dict):
            return field_data.get("value", "")
        return str(field_data) if field_data else ""
    
    # 从配置获取业务员ID
    from config import SALES_ID
    agent_id = SALES_ID or "local_system"
    
    # 获取客户姓名和公司名称
    customer_name = get_value(profile_data.get("customer_name")) or profile.get("nickname", "")
    company_name = get_value(profile_data.get("company"))  # 如果没有公司名，留空
    
    # 构建云端审批系统所需的数据格式
    cloud_data = {
        "record": {
            "id": f"LOCAL{datetime.now().strftime('%Y%m%d%H%M%S')}_{profile.get('customer_id', 'unknown')[:8]}",
            "customer_id": profile.get("customer_id", ""),
            "customer_nickname": profile.get("nickname", ""),
            "cus_name": customer_name,
            "mobile_phone": get_value(profile_data.get("phone")),
            "work_name": company_name,  # 公司名称
            "work_address": get_value(profile_data.get("address")),
            "email": get_value(profile_data.get("email")),
            "cus_intro": profile.get("notes", ""),
            "get_time": profile.get("first_contact", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "industry": get_value(profile_data.get("industry")),
            "source": get_value(profile_data.get("demand_type")) or "微信",
            "agent_id": agent_id,
            "sales_id": agent_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "approved_at": "",
            "approved_by": "",
            "tags": profile.get("tags", []),
            "priority": profile.get("priority", "中"),
            "original_profile": profile  # 保存完整画像数据
        },
        "status": "pending"  # 推送到云端后默认为待审批状态
    }
    
    return cloud_data


def push_profile_to_cloud(profile: Dict, cloud_server: str = CLOUD_APPROVAL_SERVER) -> Dict:
    """推送单个客户画像到云端审批系统"""
    try:
        # 转换数据格式
        cloud_data = profile_to_cloud_format(profile)
        
        # 调用云端API
        url = f"{cloud_server}/api/customers/sync"
        headers = {"Content-Type": "application/json"}
        
        customer_name = cloud_data["record"].get("cus_name", "未知客户")
        log(f"[CLOUD PUSH] 推送客户 {customer_name} 到云端审批系统...")
        
        resp = requests.post(
            url,
            json=cloud_data,
            headers=headers,
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            if result.get("success"):
                log(f"[CLOUD PUSH] 成功: {customer_name}")
                
                # 记录已推送的客户ID，避免重复推送
                customer_id = profile.get("customer_id", "")
                if customer_id:
                    _mark_customer_as_synced(customer_id, result.get("data", {}).get("id", ""))
                
                return {
                    "success": True,
                    "customer_name": customer_name,
                    "cloud_id": result.get("data", {}).get("id", ""),
                    "message": "推送成功"
                }
            else:
                error_msg = result.get("error", "未知错误")
                log(f"[CLOUD PUSH] 失败: {customer_name} - {error_msg}")
                return {
                    "success": False,
                    "customer_name": customer_name,
                    "error": error_msg
                }
        else:
            error_msg = f"HTTP {resp.status_code}: {resp.text}"
            log(f"[CLOUD PUSH] 失败: {customer_name} - {error_msg}")
            return {
                "success": False,
                "customer_name": customer_name,
                "error": error_msg
            }
            
    except Exception as e:
        customer_name = profile.get("nickname", "未知客户")
        log(f"[CLOUD PUSH] 异常: {customer_name} - {e}")
        return {
            "success": False,
            "customer_name": customer_name,
            "error": str(e)
        }


def push_all_profiles_to_cloud(cloud_server: str = CLOUD_APPROVAL_SERVER, 
                                filter_complete: bool = True) -> Dict:
    """批量推送所有本地客户画像到云端审批系统
    
    Args:
        cloud_server: 云端审批系统地址
        filter_complete: 是否只推送数据完整的客户
        
    Returns:
        Dict: 推送结果统计
    """
    log(f"[CLOUD PUSH] 开始批量推送本地客户画像到云端审批系统: {cloud_server}")
    
    # 加载所有本地客户画像
    profiles = load_local_customer_profiles()
    log(f"[CLOUD PUSH] 共找到 {len(profiles)} 个本地客户画像")
    
    if not profiles:
        return {
            "success": True,
            "message": "没有本地客户画像需要推送",
            "total": 0,
            "success_count": 0,
            "failed_count": 0
        }
    
    # 筛选要推送的客户
    # 第一步：先检查数据完整性
    profiles_complete = []
    skipped_incomplete = 0
    
    for profile in profiles:
        if filter_complete:
            if is_profile_complete(profile):
                profiles_complete.append(profile)
            else:
                skipped_incomplete += 1
        else:
            profiles_complete.append(profile)
    
    log(f"[CLOUD PUSH] 数据完整性检查: {len(profiles_complete)} 个完整, {skipped_incomplete} 个不完整已跳过")
    
    # 第二步：再查询云端是否存在（只对完整的数据）
    profiles_to_push = []
    skipped_synced = 0
    
    log(f"[CLOUD PUSH] 正在检查云端客户存在状态...")
    
    for profile in profiles_complete:
        customer_id = profile.get("customer_id", "")
        
        # 查询云端是否存在该客户
        if customer_id and check_customer_exists_in_cloud(customer_id, cloud_server):
            skipped_synced += 1
            continue
        
        profiles_to_push.append(profile)
    
    log(f"[CLOUD PUSH] 筛选后: {len(profiles_to_push)} 个待推送, {skipped_incomplete} 个数据不完整已跳过, {skipped_synced} 个云端已存在已跳过")
    
    # 批量推送
    success_count = 0
    failed_count = 0
    success_list = []
    failed_list = []
    
    for profile in profiles_to_push:
        result = push_profile_to_cloud(profile, cloud_server)
        
        if result["success"]:
            success_count += 1
            success_list.append({
                "name": result["customer_name"],
                "cloud_id": result.get("cloud_id", "")
            })
        else:
            failed_count += 1
            failed_list.append({
                "name": result["customer_name"],
                "error": result.get("error", "")
            })
    
    log(f"[CLOUD PUSH] 批量推送完成: 成功 {success_count} 个, 失败 {failed_count} 个")
    
    return {
        "success": True,
        "message": f"批量推送完成: 成功 {success_count} 个, 失败 {failed_count} 个, 跳过 {skipped_synced} 个已推送",
        "total": len(profiles_to_push),
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_incomplete": skipped_incomplete,
        "skipped_synced": skipped_synced,
        "success_list": success_list,
        "failed_list": failed_list,
        "cloud_server": cloud_server
    }


def push_profile_by_customer_id(customer_id: str, cloud_server: str = CLOUD_APPROVAL_SERVER) -> Dict:
    """根据客户ID推送指定客户画像到云端审批系统"""
    # 加载所有本地客户画像
    profiles = load_local_customer_profiles()
    
    # 查找指定客户
    target_profile = None
    for profile in profiles:
        if profile.get("customer_id") == customer_id:
            target_profile = profile
            break
    
    if not target_profile:
        return {
            "success": False,
            "error": f"未找到客户ID为 {customer_id} 的画像数据"
        }
    
    # 推送该客户
    return push_profile_to_cloud(target_profile, cloud_server)
