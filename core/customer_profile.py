"""
客户画像管理系统
用于收集、存储和更新客户画像信息
"""
import os
import json
from datetime import datetime
from typing import Dict, Optional, List, Any

# 客户画像存储目录
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chat_history")
os.makedirs(PROFILE_DIR, exist_ok=True)


def get_profile_path(nickname: str) -> str:
    """获取客户画像文件路径"""
    # Windows文件名非法字符: \ / : * ? " < > |
    illegal_chars = '\\/:*?"<>|'
    safe_name = "".join(c for c in nickname if c not in illegal_chars).strip()
    # 如果过滤后为空，使用MD5编码
    if not safe_name:
        import hashlib
        safe_name = hashlib.md5(nickname.encode()).hexdigest()[:8]
    return os.path.join(PROFILE_DIR, f"{safe_name}_profile.json")


def load_profile(nickname: str) -> Optional[Dict]:
    """加载客户画像"""
    profile_path = get_profile_path(nickname)
    if not os.path.exists(profile_path):
        return None
    
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_profile(nickname: str, profile: Dict) -> bool:
    """保存客户画像"""
    profile_path = get_profile_path(nickname)
    try:
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def create_profile(nickname: str, customer_id: str = "") -> Dict:
    """创建新客户画像"""
    now = datetime.now().strftime("%Y-%m-%d")
    profile = {
        "customer_id": customer_id,
        "nickname": nickname,
        "first_contact": now,
        "last_contact": now,
        "profile": {
            "customer_type": {"value": "未知", "source": "未知", "confidence": 0},
            "industry": {"value": "", "source": "未知", "confidence": 0},
            "business": {"value": "", "source": "未知", "confidence": 0},
            "demand_type": {"value": "未知", "source": "未知", "confidence": 0},
            "quantity": {"value": "", "source": "未知", "confidence": 0},
            "pain_points": {"value": "", "source": "未知", "confidence": 0},
            "usage_scenario": {"value": "", "source": "未知", "confidence": 0},
            "budget": {"value": "", "source": "未知", "confidence": 0}
        },
        "interactions": [],
        "orders": [],
        "tags": [],
        "notes": "",
        "priority": "中"
    }
    save_profile(nickname, profile)
    return profile


def update_profile_field(nickname: str, field: str, value: str, source: str = "客户自述", confidence: float = 0.8) -> bool:
    """更新客户画像某个字段"""
    profile = load_profile(nickname)
    if not profile:
        return False
    
    if field in profile["profile"]:
        profile["profile"][field] = {
            "value": value,
            "source": source,
            "confidence": confidence
        }
        profile["last_contact"] = datetime.now().strftime("%Y-%m-%d")
        return save_profile(nickname, profile)
    return False


def add_interaction(nickname: str, interaction_type: str, content: str, 
                   products: List[str] = None, intention: str = "", next_action: str = "") -> bool:
    """添加交互记录"""
    profile = load_profile(nickname)
    if not profile:
        profile = create_profile(nickname)
    
    interaction = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "type": interaction_type,
        "content": content,
        "products_mentioned": products or [],
        "intention": intention,
        "next_action": next_action
    }
    profile["interactions"].append(interaction)
    profile["last_contact"] = datetime.now().strftime("%Y-%m-%d")
    return save_profile(nickname, profile)


def add_tag(nickname: str, tag: str) -> bool:
    """添加客户标签"""
    profile = load_profile(nickname)
    if not profile:
        return False
    
    if tag not in profile["tags"]:
        profile["tags"].append(tag)
        return save_profile(nickname, profile)
    return True


def get_profile_summary(nickname: str) -> str:
    """获取客户画像摘要（用于上下文提示）"""
    profile = load_profile(nickname)
    if not profile:
        return ""
    
    p = profile["profile"]
    summary_parts = []
    
    if p["customer_type"]["value"] != "未知":
        summary_parts.append(f"客户类型：{p['customer_type']['value']}")
    if p["industry"]["value"]:
        summary_parts.append(f"行业：{p['industry']['value']}")
    if p["demand_type"]["value"] != "未知":
        summary_parts.append(f"需求类型：{p['demand_type']['value']}")
    if p["quantity"]["value"]:
        summary_parts.append(f"需求量：{p['quantity']['value']}")
    if p["budget"]["value"]:
        summary_parts.append(f"预算：{p['budget']['value']}")
    if p["pain_points"]["value"]:
        summary_parts.append(f"痛点：{p['pain_points']['value']}")
    
    return " | ".join(summary_parts) if summary_parts else "新客户，画像待收集"


def list_all_profiles() -> List[Dict]:
    """列出所有客户画像摘要"""
    profiles = []
    for fname in os.listdir(PROFILE_DIR):
        if fname.endswith("_profile.json"):
            nickname = fname.replace("_profile.json", "")
            profile = load_profile(nickname)
            if profile:
                profiles.append({
                    "nickname": nickname,
                    "priority": profile.get("priority", "中"),
                    "last_contact": profile.get("last_contact", ""),
                    "summary": get_profile_summary(nickname)
                })
    return profiles


# 测试
if __name__ == "__main__":
    # 测试获取所有客户画像
    profiles = list_all_profiles()
    print("客户画像列表：")
    for p in profiles:
        print(f"  - {p['nickname']} ({p['priority']}): {p['summary']}")
