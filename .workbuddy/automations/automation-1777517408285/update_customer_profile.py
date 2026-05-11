#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新客户画像脚本
从对话记录中提取关键信息，更新客户画像文件

使用方式:
    python update_customer_profile.py [--hours 1] [--log-file path] [--dry-run]
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 项目路径（向上4层：automation-xxx > automations > .workbuddy > Claw）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Claw项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
CHAT_HISTORY_DIR = os.path.join(BASE_DIR, "data", "chat_history")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DATA_LOGS_DIR = os.path.join(BASE_DIR, "data", "logs")

# 确保目录存在
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


def log(message: str):
    """打印日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_profile_path(nickname: str) -> str:
    """获取客户画像文件路径"""
    illegal_chars = '\\/:*?"<>|'
    safe_name = "".join(c for c in nickname if c not in illegal_chars).strip()
    if not safe_name:
        import hashlib
        safe_name = hashlib.md5(nickname.encode()).hexdigest()[:8]
    return os.path.join(CHAT_HISTORY_DIR, f"{safe_name}_profile.json")


def load_profile(nickname: str) -> Optional[Dict]:
    """加载客户画像"""
    profile_path = get_profile_path(nickname)
    if not os.path.exists(profile_path):
        return None
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"加载画像失败 {nickname}: {e}")
        return None


def save_profile(nickname: str, profile: Dict) -> bool:
    """保存客户画像"""
    profile_path = get_profile_path(nickname)
    try:
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        log(f"保存画像失败 {nickname}: {e}")
        return False


def create_profile(nickname: str) -> Dict:
    """创建新客户画像"""
    now = datetime.now().strftime("%Y-%m-%d")
    profile = {
        "customer_id": "",
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


def extract_info_from_conversation(conversation: str) -> Dict:
    """从对话中提取关键信息"""
    info = {
        "products": [],
        "quantity": "",
        "budget": "",
        "address": "",
        "intention": "",
        "price_negotiation": False
    }
    
    # 提取产品型号
    product_patterns = [
        r'(T\d+)', r'(F\d+)', r'(E\d+)', 
        r'型号[：:]\s*(\w+)', r'(\w+)\s*型号'
    ]
    for pattern in product_patterns:
        matches = re.findall(pattern, conversation, re.IGNORECASE)
        info["products"].extend([m.upper() for m in matches if m.upper() not in info["products"]])
    
    # 提取数量
    quantity_patterns = [
        r'(\d+)\s*(?:套|台|张|个)',
        r'数量[：:]\s*(\d+)',
        r'(\d+)\s*套'
    ]
    for pattern in quantity_patterns:
        match = re.search(pattern, conversation)
        if match:
            info["quantity"] = match.group(1) + "套"
            break
    
    # 提取预算/价格
    budget_patterns = [
        r'(\d+)\s*元',
        r'预算[：:]\s*(\d+)',
        r'价格[：:]\s*(\d+)',
        r'(\d+)\s*万'
    ]
    for pattern in budget_patterns:
        match = re.search(pattern, conversation)
        if match:
            value = match.group(1)
            if '万' in match.group(0):
                info["budget"] = value + "万元"
            else:
                info["budget"] = value + "元"
            break
    
    # 提取地址
    address_patterns = [
        r'地址[：:]\s*([^\n\s]+)',
        r'收货[：:]\s*([^\n\s]+)',
        r'([\u4e00-\u9fa5]{2,}[省市区][^\n\s]*)'
    ]
    for pattern in address_patterns:
        match = re.search(pattern, conversation)
        if match:
            info["address"] = match.group(1)
            break
    
    # 判断意向度
    if re.search(r'成交|下单|付款|合同|确认', conversation):
        info["intention"] = "高意向，已确认订单"
    elif re.search(r'考虑|商量|对比|再看看', conversation):
        info["intention"] = "中意向，考虑中"
    elif re.search(r'价格|优惠|便宜|贵', conversation):
        info["intention"] = "中意向，价格谈判中"
        info["price_negotiation"] = True
    elif re.search(r'你好|咨询|了解|什么', conversation):
        info["intention"] = "低意向，咨询阶段"
    
    return info


def update_customer_profile(nickname: str, conversation: str, dry_run: bool = False) -> bool:
    """更新客户画像"""
    # 加载或创建画像
    profile = load_profile(nickname)
    if not profile:
        log(f"创建新客户画像: {nickname}")
        profile = create_profile(nickname)
    
    # 提取信息
    info = extract_info_from_conversation(conversation)
    
    # 更新last_contact
    today = datetime.now().strftime("%Y-%m-%d")
    profile["last_contact"] = today
    
    # 更新profile字段
    if info["quantity"] and not profile["profile"]["quantity"]["value"]:
        profile["profile"]["quantity"] = {
            "value": info["quantity"],
            "source": "对话分析",
            "confidence": 0.8
        }
    
    if info["budget"] and not profile["profile"]["budget"]["value"]:
        profile["profile"]["budget"] = {
            "value": info["budget"],
            "source": "对话分析",
            "confidence": 0.8
        }
    
    if info["address"] and not profile["profile"].get("address", {}).get("value"):
        if "address" not in profile["profile"]:
            profile["profile"]["address"] = {"value": "", "source": "", "confidence": 0}
        profile["profile"]["address"] = {
            "value": info["address"],
            "source": "对话分析",
            "confidence": 0.8
        }
    
    # 添加交互记录（只记录关键交互，不是每次回复都记录）
    # 判断是否为关键交互：有产品提及、有数量、有预算、或高意向
    is_key_interaction = (
        info["products"] or 
        info["quantity"] or 
        info["budget"] or 
        "高意向" in info["intention"] or
        info["price_negotiation"]
    )
    
    if is_key_interaction:
        # 生成摘要
        summary_parts = []
        if info["products"]:
            summary_parts.append(f"咨询产品: {', '.join(info['products'])}")
        if info["quantity"]:
            summary_parts.append(f"数量: {info['quantity']}")
        if info["budget"]:
            summary_parts.append(f"预算: {info['budget']}")
        if info["intention"]:
            summary_parts.append(f"意向: {info['intention']}")
        
        content = "；".join(summary_parts) if summary_parts else "客户咨询"
        
        interaction = {
            "date": today,
            "type": "咨询" if "低意向" in info["intention"] else "询价" if "中意向" in info["intention"] else "下单" if "高意向" in info["intention"] else "咨询",
            "content": content,
            "products_mentioned": info["products"],
            "intention": info["intention"] or "已回复客户",
            "next_action": "等待客户回复"
        }
        profile["interactions"].append(interaction)
        log(f"  记录关键交互: {content[:50]}...")
    
    # 更新tags
    if info["price_negotiation"] and "价格敏感" not in profile["tags"]:
        profile["tags"].append("价格敏感")
    
    if info["products"] and any(p in ["T524", "T523", "T412"] for p in info["products"]) and "经济款需求" not in profile["tags"]:
        profile["tags"].append("经济款需求")
    
    # 更新priority
    if "高意向" in info["intention"]:
        profile["priority"] = "高"
    elif "中意向" in info["intention"]:
        profile["priority"] = "中"
    else:
        profile["priority"] = "低"
    
    # 保存
    if not dry_run:
        success = save_profile(nickname, profile)
        if success:
            log(f"✅ 已更新客户画像: {nickname}")
            return True
        else:
            log(f"❌ 保存失败: {nickname}")
            return False
    else:
        log(f"[DRY RUN] 将更新客户画像: {nickname}")
        log(f"[DRY RUN] 提取信息: {json.dumps(info, ensure_ascii=False)}")
        return True


def read_conversations_from_log(log_file: str, hours: int = 1) -> List[Dict]:
    """从日志文件读取最近的对话记录"""
    conversations = []
    
    if not os.path.exists(log_file):
        log(f"日志文件不存在: {log_file}")
        return conversations
    
    # 计算时间范围
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # 使用正则表达式提取对话
        # 格式1: [日期 时间] New msg [昵称]: 内容 type=text
        # 格式2: [日期 时间] New msg [昵称]: 昵称: 内容 type=text (消息内容重复了昵称)
        patterns = [
            r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\]\s+New msg\s+\[([^\]]+)\]:\s+[^\:]+:\s+(.+?)\s+type=',
            r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\]\s+New msg\s+\[([^\]]+)\]:\s+(.+?)\s+type='
        ]
        
        matches = []
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                break
        
        for date_str, time_str, nickname, message in matches:
            # 解析时间
            msg_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            
            # 检查是否在时间范围内
            if msg_time >= cutoff_time:
                conversations.append({
                    "nickname": nickname,
                    "message": message,
                    "time": msg_time
                })
        
        log(f"从日志中提取了 {len(conversations)} 条对话记录")
        
    except Exception as e:
        log(f"读取日志失败: {e}")
    
    return conversations


def group_conversations_by_nickname(conversations: List[Dict]) -> Dict[str, str]:
    """按昵称分组对话"""
    grouped = {}
    for conv in conversations:
        nickname = conv["nickname"]
        if nickname not in grouped:
            grouped[nickname] = []
        grouped[nickname].append(conv["message"])
    
    # 合并每个客户的对话
    result = {}
    for nickname, messages in grouped.items():
        result[nickname] = "\n".join(messages)
    
    return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='自动更新客户画像')
    parser.add_argument('--hours', type=int, default=1, help='读取最近N小时的对话（默认1小时）')
    parser.add_argument('--log-file', type=str, help='指定日志文件路径')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际修改文件')
    args = parser.parse_args()
    
    log("=" * 60)
    log("自动更新客户画像任务开始")
    log(f"时间范围: 最近 {args.hours} 小时")
    log("=" * 60)
    
    # 确定日志文件
    if args.log_file:
        log_file = args.log_file
    else:
        # 尝试默认日志文件
        today = datetime.now().strftime("%Y%m%d")
        possible_logs = [
            os.path.join(LOGS_DIR, "weflow-wb-bridge.log"),
            os.path.join(DATA_LOGS_DIR, f"toolserver_{today}.log"),
        ]
        log_file = None
        for path in possible_logs:
            if os.path.exists(path):
                log_file = path
                break
        
        if not log_file:
            log("❌ 未找到日志文件")
            return
    
    log(f"使用日志文件: {log_file}")
    
    # 读取对话记录
    conversations = read_conversations_from_log(log_file, args.hours)
    
    if not conversations:
        log("未找到新的对话记录")
        log("任务结束")
        return
    
    # 按昵称分组
    grouped = group_conversations_by_nickname(conversations)
    
    log(f"需要更新 {len(grouped)} 个客户画像")
    
    # 更新每个客户的画像
    success_count = 0
    for nickname, conversation in grouped.items():
        log(f"\n处理客户: {nickname}")
        if update_customer_profile(nickname, conversation, args.dry_run):
            success_count += 1
    
    log("\n" + "=" * 60)
    log(f"任务完成: 成功更新 {success_count}/{len(grouped)} 个客户画像")
    log("=" * 60)


if __name__ == "__main__":
    main()
