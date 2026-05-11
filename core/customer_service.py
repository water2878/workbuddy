"""
客户记忆服务 — 客户信息、偏好、历史交易记录
简单的 JSON 文件存储，AI 读写。
"""
import os
import json
import time
from pathlib import Path
from typing import Optional

from config import CUSTOMERS_DIR, log


def _customer_file(contact_id: str) -> str:
    """获取客户数据文件路径"""
    # 清理文件名中的特殊字符
    safe_id = contact_id.replace("@chatroom", "_group").replace("/", "_").replace("\\", "_")
    return os.path.join(CUSTOMERS_DIR, f"{safe_id}.json")


def get_customer(contact_id: str) -> dict:
    """获取客户信息"""
    path = _customer_file(contact_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # 返回空结构
    return {
        "id": contact_id,
        "name": "",
        "notes": "",
        "preferences": {},
        "orders": [],
        "last_contact": None,
        "created_at": None,
    }


def save_customer(contact_id: str, data: dict) -> dict:
    """保存客户信息"""
    path = _customer_file(contact_id)

    # 合并已有数据
    existing = get_customer(contact_id)
    existing.update(data)
    existing["id"] = contact_id
    existing["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if not existing.get("created_at"):
        existing["created_at"] = existing["updated_at"]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return existing


def update_customer_notes(contact_id: str, notes: str) -> dict:
    """更新客户备注"""
    customer = get_customer(contact_id)
    customer["notes"] = notes
    return save_customer(contact_id, customer)


def add_customer_order(contact_id: str, order: dict) -> dict:
    """添加客户订单记录"""
    customer = get_customer(contact_id)
    order["added_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    customer.setdefault("orders", []).append(order)
    return save_customer(contact_id, customer)


def set_customer_preference(contact_id: str, key: str, value: str) -> dict:
    """设置客户偏好"""
    customer = get_customer(contact_id)
    customer.setdefault("preferences", {})[key] = value
    return save_customer(contact_id, customer)


def list_customers() -> list[dict]:
    """列出所有客户"""
    customers = []
    if not os.path.isdir(CUSTOMERS_DIR):
        return customers

    for fname in os.listdir(CUSTOMERS_DIR):
        if fname.endswith(".json"):
            path = os.path.join(CUSTOMERS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    customers.append(data)
            except (json.JSONDecodeError, IOError):
                pass

    return sorted(customers, key=lambda c: c.get("updated_at", ""), reverse=True)


def search_customers(query: str) -> list[dict]:
    """搜索客户（按名称/备注模糊匹配）"""
    all_customers = list_customers()
    query_lower = query.lower()
    results = []
    for c in all_customers:
        if (query_lower in (c.get("name", "")).lower() or
            query_lower in (c.get("notes", "")).lower() or
            query_lower in (c.get("id", "")).lower()):
            results.append(c)
    return results


def touch_customer(contact_id: str, name: str = "") -> dict:
    """记录客户最近联系时间（收到消息时调用）"""
    customer = get_customer(contact_id)
    if name and not customer.get("name"):
        customer["name"] = name
    customer["last_contact"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return save_customer(contact_id, customer)
