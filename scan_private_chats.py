#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描微信私聊列表，排除内部/家人/系统号，按优先级排序
用法: python scan_private_chats.py [--limit 200]
输出: JSON格式的排序结果到 stdout
"""
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, 'core')
from weflow_client import WeFlowClient
from customer_profile import load_profile, PROFILE_DIR
import config

# ===== 配置 =====
COOLDOWN_DAYS = 30          # 主动消息冷却期（天），同一人至少间隔1个月再联系
SILENT_DAYS_THRESHOLD = 30  # "沉默"判定阈值（天），优先钓沉默1月+
MAX_GET_LIMIT = 200         # 拉取会话上限
FALLBACK_IF_NO_SILENT = True  # 无沉默1月+客户时，降级到沉默最久

# 排除联系人列表
SKIP_FILE = os.path.join(os.path.dirname(__file__), "data", "skip_contacts.json")
PROACTIVE_LOG = os.path.join(os.path.dirname(__file__), "data", "proactive_chat_log.json")

# 额外的排除关键词（昵称包含这些的跳过）
EXTRA_SKIP_KEYWORDS = [
    "招聘", "猎头", "快递", "超市", "网咖", "麻将", "hr",
    "畅腾", "智能升降桌李生", "畅腾商用升降桌",
    "文件传输助手", "微信", "腾讯", "京东",
    "客服", "测试", "test",
    # 家庭成员
    "妈", "姐", "舅",
    # 劳务中介
    "劳务", "中介", "企业汇总", "电子厂", "汽车厂",
]

# 公众号/系统号前缀
SKIP_PUBLIC_ACCOUNT_PREFIXES = ["gh_", "wxid_test"]

# ===== 工具函数 =====
def load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def should_skip(nickname: str, username: str = "") -> bool:
    """判断是否应跳过该联系人"""
    skip_data = load_json(SKIP_FILE, {"skip_nicks": [], "skip_usernames": []})
    skip_nicks = skip_data.get("skip_nicks", [])
    skip_usernames = skip_data.get("skip_usernames", [])

    # 按 username 排除（如 wxid_anahkoom2m6222 等系统号）
    if username and username in skip_usernames:
        return True

    # 精确匹配昵称
    if nickname in skip_nicks:
        return True

    # 公众号/系统号前缀
    lower_nick = nickname.lower()
    for prefix in SKIP_PUBLIC_ACCOUNT_PREFIXES:
        if lower_nick.startswith(prefix):
            return True

    # 关键词匹配
    lower = nickname.lower()
    for kw in EXTRA_SKIP_KEYWORDS:
        if kw.lower() in lower:
            return True

    return False


def get_proactive_time(nickname: str) -> str:
    """获取上次主动联系的日期"""
    log = load_json(PROACTIVE_LOG, {})
    return log.get(nickname, "")


def in_cooldown(nickname: str) -> bool:
    """判断是否在冷却期内（距上次主动联系 < COOLDOWN_DAYS 天）"""
    last_time = get_proactive_time(nickname)
    if not last_time:
        return False
    try:
        last_dt = datetime.strptime(last_time, "%Y-%m-%d %H:%M")
        return (datetime.now() - last_dt).days < COOLDOWN_DAYS
    except:
        try:
            last_dt = datetime.strptime(last_time, "%Y-%m-%d")
            return (datetime.now() - last_dt).days < COOLDOWN_DAYS
        except:
            return False


def days_since(date_str: str) -> int:
    """计算距离某个日期的天数"""
    if not date_str:
        return 999
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - dt).days
    except:
        return 999


def compute_priority_score(profile: dict) -> tuple:
    """
    计算优先级分数，返回 (sort_key, label)
    sort_key 越小越优先:
      0 = 下过单+沉默>=30天
      1 = 有产品意向+沉默>=30天
      2 = 沉默最久（按天数降序）
      3 = 有订单但不足30天
      4 = 有意向但不足30天
      5 = 其他
    """
    if not profile:
        return (99, "无画像")

    orders = profile.get("orders", [])
    tags = profile.get("tags", [])
    p = profile.get("profile", {})
    last_contact = profile.get("last_contact", "")
    silent_days = days_since(last_contact)
    priority = profile.get("priority", "中")

    # 取 profile 中 quantity 的值
    qty_field = p.get("quantity", {})
    qty_value = qty_field.get("value", "") if isinstance(qty_field, dict) else str(qty_field)
    
    # 取 interested_models（如果有）
    interested = []
    for interaction in profile.get("interactions", []):
        products = interaction.get("products_mentioned", [])
        interested.extend(products)
    interested = list(set(interested))

    has_order = len(orders) > 0
    has_intent = bool(interested) or bool(qty_value) or priority == "高"

    if has_order and silent_days >= SILENT_DAYS_THRESHOLD:
        return (0, f"下过单+沉默{silent_days}天")
    elif has_intent and silent_days >= SILENT_DAYS_THRESHOLD:
        return (1, f"有意向+沉默{silent_days}天")
    elif silent_days >= SILENT_DAYS_THRESHOLD:
        return (2, f"沉默{silent_days}天")
    elif has_order:
        return (3, f"有订单+{silent_days}天")
    elif has_intent:
        return (4, f"有意向+{silent_days}天")
    else:
        return (5 + max(0, 999 - silent_days), f"其他+{silent_days}天")


# ===== 主流程 =====
def scan():
    client = WeFlowClient(base_url=config.WEFLOW_BASE, token=config.WEFLOW_TOKEN)

    # 1. 获取会话列表
    #    API docs: type==2 = 群聊, sessionType="private"/"group"/"channel" (实际返回)
    #    用 sessionType 字段过滤（如果存在），否则用 type 字段
    print("[scan] 获取会话列表...", file=sys.stderr)
    sessions_data = client.get_sessions(limit=MAX_GET_LIMIT)
    sessions = sessions_data.get("sessions", []) or sessions_data.get("data", [])

    # 2. 只保留私聊
    #    - sessionType == "private" (实际API返回)
    #    - type != 2 (API文档方式, 2=群聊)
    #    - username 不含 @chatroom (最可靠的后备方式)
    all_contacts = {}  # username -> {nickname, username, last_msg_date}
    type_stats = {"private": 0, "group": 0, "channel": 0, "other": 0}

    for s in sessions:
        username = s.get("username", "")
        session_type = s.get("sessionType", "").lower()

        # 分类统计
        if session_type:
            type_stats[session_type] = type_stats.get(session_type, 0) + 1
        elif s.get("type") == 2:
            type_stats["group"] = type_stats.get("group", 0) + 1
            session_type = "group"
        elif "@chatroom" in username:
            type_stats["group"] = type_stats.get("group", 0) + 1
            session_type = "group"
        else:
            type_stats["other"] = type_stats.get("other", 0) + 1
            session_type = "unknown"

        # 跳过群聊/公众号
        if session_type in ("group", "channel"):
            continue

        nickname = s.get("displayName", "") or s.get("nickname", "") or s.get("name", "")
        last_ts = s.get("lastTimestamp", 0)
        if username and nickname:
            all_contacts[username] = {
                "nickname": nickname,
                "username": username,
                "last_timestamp": last_ts,
                "last_msg_date": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M") if last_ts else "未知"
            }

    print(f"[scan] 会话分类: {type_stats}", file=sys.stderr)
    print(f"[scan] 私聊联系人: {len(all_contacts)} 个", file=sys.stderr)

    # 4. 排除
    filtered = []
    for username, info in all_contacts.items():
        nick = info["nickname"]
        if should_skip(nick, username):
            continue
        # 排除自己的号
        if "李生" in nick or username.startswith("wxid_test"):
            continue
        filtered.append(info)

    print(f"[scan] 排除后剩余 {len(filtered)} 个", file=sys.stderr)

    # 5. 加载画像 + 计算优先级
    results = []
    for info in filtered:
        nick = info["nickname"]
        profile = load_profile(nick)
        last_contact = profile.get("last_contact", "") if profile else ""
        silent_days = days_since(last_contact)
        score, label = compute_priority_score(profile)
        in_cd = in_cooldown(nick)

        orders = profile.get("orders", []) if profile else []
        p = profile.get("profile", {}) if profile else {}
        qty = p.get("quantity", {}).get("value", "") if isinstance(p.get("quantity"), dict) else ""

        # 提取意向型号
        interested = []
        if profile:
            for ix in profile.get("interactions", []):
                for pm in ix.get("products_mentioned", []):
                    if pm and pm not in interested:
                        interested.append(pm)

        results.append({
            "nickname": nick,
            "username": info["username"],
            "score": score,
            "label": label,
            "silent_days": silent_days,
            "last_contact": last_contact or info.get("last_msg_date", "未知"),
            "last_wechat_msg": info.get("last_msg_date", "未知"),
            "has_profile": profile is not None,
            "has_orders": len(orders) > 0,
            "order_count": len(orders),
            "interested_models": interested,
            "quantity": qty,
            "priority": profile.get("priority", "中") if profile else "中",
            "tags": profile.get("tags", []) if profile else [],
            "notes": profile.get("notes", "")[:200] if profile else "",
            "in_cooldown": in_cd,
            "last_proactive": get_proactive_time(nick),
        })

    # 6. 排序: score 升序, silent_days 降序（同分时沉默更久的优先）
    results.sort(key=lambda r: (r["score"], -r["silent_days"]))

    # 7. 输出 JSON
    output = {
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_scanned": len(all_contacts),
        "total_filtered": len(filtered),
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    scan()
