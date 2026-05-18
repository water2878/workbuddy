#!/usr/bin/env python3
"""
自动更新客户画像脚本
从日志文件读取最近1小时的对话记录，分析并更新客户画像
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import re

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
CHAT_HISTORY_DIR = PROJECT_ROOT / "data" / "chat_history"

# 昵称黑名单：系统日志中的常见标签，不是真实客户昵称
NICKNAME_BLACKLIST = {
    # 日期时间前缀（timestamp in brackets）
    "2026-05-18", "2026-05-17", "2026-05-16", "2026-05-15",
    "2026-05-14", "2026-05-13", "2026-05-12", "2026-05-11",
    # 常见系统标签
    "INFO", "WARN", "ERROR", "DEBUG", "合同", "生成合同",
    "产品", "同步", "推送", "通知", "发送", "接收",
    "微信", "消息", "客户", "用户", "系统", "自动",
}

# 日志行前缀黑名单正则：系统日志行开头的常见标签（用于过滤整行）
SYSTEM_LOG_PREFIXES = (
    r'\[INFO\]', r'\[WARN\]', r'\[ERROR\]', r'\[DEBUG\]',
    r'\[合同\]', r'\[产品\]', r'\[微信\]', r'\[同步\]',
    r'\[推送\]', r'\[通知\]', r'\[生成合同\]',
    r'\[[\d]{4}-[\d]{2}-[\d]{2}\s+[\d]{2}:[\d]{2}:[\d]{2}\]',  # 日期时间前缀
)

# 昵称过滤正则：非客户昵称的模式
INVALID_NICKNAME_PATTERNS = [
    re.compile(r'^[\d]{4}-[\d]{2}-[\d]{2}$'),           # 日期: 2026-05-18
    re.compile(r'^[0-9a-fA-F]{8,}$'),                   # 十六进制ID
    re.compile(r'^(INFO|WARN|ERROR|DEBUG)$'),           # 系统标签
    re.compile(r'^[\u4e00-\u9fff]{1,4}$'),               # 纯短汉字(1-4字)，通常是系统词
]


def is_valid_customer_nickname(nickname):
    """判断昵称是否为有效客户昵称（而非系统标签）"""
    if not nickname or not nickname.strip():
        return False
    nickname = nickname.strip()
    # 黑名单直接排除
    if nickname in NICKNAME_BLACKLIST:
        return False
    # 排除常见系统词
    for pattern in INVALID_NICKNAME_PATTERNS:
        if pattern.match(nickname):
            return False
    # 昵称不能太短（至少2个可见字符）
    visible_chars = re.sub(r'\s', '', nickname)
    if len(visible_chars) < 2:
        return False
    return True


def is_system_log_line(line):
    """判断日志行是否为系统日志（而非客户对话）"""
    for prefix in SYSTEM_LOG_PREFIXES:
        if re.match(prefix, line.strip()):
            return True
    return False

def get_log_file_path(date_str=None):
    """获取指定日期的日志文件路径"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    return LOGS_DIR / f"claw_{date_str}.log"

def read_recent_logs(hours=1):
    """读取最近N小时的日志记录"""
    log_file = get_log_file_path()

    if not log_file.exists():
        print(f"⚠️ 日志文件不存在: {log_file}")
        return []

    # 读取日志内容
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"❌ 读取日志文件失败: {e}")
        return []

    if not lines:
        print(f"⚠️ 日志文件为空: {log_file}")
        return []

    # 计算时间阈值
    time_threshold = datetime.now() - timedelta(hours=hours)

    # 解析日志记录（假设日志格式包含时间戳）
    recent_logs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 跳过系统日志行（非客户对话）
        if is_system_log_line(line):
            continue

        # 尝试从日志行提取时间戳（格式：2026-05-15 14:30:25）
        time_match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        if time_match:
            try:
                log_time = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S")
                if log_time >= time_threshold:
                    recent_logs.append(line)
            except ValueError:
                # 没有时间戳，假设是最近的日志
                recent_logs.append(line)
        else:
            # 没有时间戳，假设是最近的日志
            recent_logs.append(line)

    print(f"📋 找到 {len(recent_logs)} 条最近 {hours} 小时的日志记录")
    return recent_logs

def extract_customer_info(log_lines):
    """从日志中提取客户信息"""
    customers = {}

    for line in log_lines:
        # 匹配客户消息格式: [昵称] 内容
        match = re.search(r'\[([^\]]+)\]\s*(.*)', line)
        if match:
            raw_nickname = match.group(1)
            content = match.group(2)

            # ⚠️ 过滤非客户昵称（系统标签、时间戳等）
            if not is_valid_customer_nickname(raw_nickname):
                continue

            nickname = raw_nickname

            if nickname not in customers:
                customers[nickname] = {
                    "messages": [],
                    "last_message": content,
                    "message_count": 0
                }

            customers[nickname]["messages"].append(content)
            customers[nickname]["last_message"] = content
            customers[nickname]["message_count"] += 1

    return customers

def analyze_customer_intent(messages):
    """分析客户意向度和需求"""
    all_text = " ".join(messages).lower()

    # 意向度分析
    intention = "low"
    if any(word in all_text for word in ["成交", "合同", "付款", "下单", "确定"]):
        intention = "high"
    elif any(word in all_text for word in ["考虑", "报价", "价格", "多少钱", "样品"]):
        intention = "medium"

    # 提取产品信息
    products = []
    if "t621" in all_text or "椭圆管" in all_text:
        products.append("T621")
    if "t412" in all_text or "方管" in all_text:
        products.append("T412")
    if "t523" in all_text or "t524" in all_text or "单电机" in all_text:
        products.append("T523/T524")

    # 提取数量
    quantity = None
    qty_match = re.search(r'(\d+)\s*(套|台|张)', all_text)
    if qty_match:
        quantity = int(qty_match.group(1))

    # 提取预算
    budget = None
    budget_match = re.search(r'(\d+)\s*(元|块)', all_text)
    if budget_match:
        budget = f"{budget_match.group(1)}元"

    return {
        "intention": intention,
        "products": products,
        "quantity": quantity,
        "budget": budget
    }

def load_customer_profile(nickname):
    """加载客户画像文件"""
    # 清理文件名中的非法字符
    safe_nickname = re.sub(r'[<>:"/\\|?*]', '_', nickname)
    profile_path = CHAT_HISTORY_DIR / f"{safe_nickname}_profile.json"

    if profile_path.exists():
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f), profile_path
        except Exception as e:
            print(f"⚠️ 读取客户画像失败: {e}")

    return None, profile_path

def create_default_profile(nickname):
    """创建默认客户画像"""
    return {
        "nickname": nickname,
        "customer_name": "",
        "company": "",
        "contact": "",
        "phone": "",
        "email": "",
        "address": "",
        "profile": {
            "type": "unknown",  # B端/C端
            "industry": "",
            "needs": "",
            "budget": None,
            "quantity": None,
            "pain_points": ""
        },
        "interactions": [],
        "tags": [],
        "priority": "low",
        "status": "new",
        "last_contact": datetime.now().strftime("%Y-%m-%d"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def update_profile_with_analysis(profile, analysis, messages, nickname):
    """根据分析结果更新客户画像"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 更新最后联系时间
    profile["last_contact"] = date_str
    profile["updated_at"] = time_str

    # 更新profile字段
    if analysis["budget"]:
        profile["profile"]["budget"] = analysis["budget"]
    if analysis["quantity"]:
        profile["profile"]["quantity"] = analysis["quantity"]
    if analysis["products"]:
        profile["profile"]["needs"] = f"咨询产品: {', '.join(analysis['products'])}"

    # 更新优先级
    if analysis["intention"] == "high":
        profile["priority"] = "high"
        profile["status"] = "negotiating"
    elif analysis["intention"] == "medium":
        profile["priority"] = "medium"
        if profile["status"] == "new":
            profile["status"] = "contacted"

    # 添加交互记录
    interaction = {
        "date": time_str,
        "type": "chat",
        "content": messages[-1] if messages else "",
        "products_mentioned": analysis["products"],
        "intention": analysis["intention"],
        "next_action": "follow_up" if analysis["intention"] in ["medium", "high"] else "wait"
    }
    profile["interactions"].append(interaction)

    # 更新标签
    if analysis["intention"] == "high" and "高意向" not in profile["tags"]:
        profile["tags"].append("高意向")
    if analysis["products"] and "有产品需求" not in profile["tags"]:
        profile["tags"].append("有产品需求")

    return profile

def save_customer_profile(profile, profile_path):
    """保存客户画像文件"""
    try:
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"✅ 客户画像已更新: {profile_path.name}")
        return True
    except Exception as e:
        print(f"❌ 保存客户画像失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="自动更新客户画像")
    parser.add_argument("--hours", type=int, default=1, help="读取最近N小时的日志（默认1小时）")
    args = parser.parse_args()

    print(f"🚀 开始执行客户画像更新任务...")
    print(f"📅 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏰ 读取最近 {args.hours} 小时的日志\n")

    # 读取最近日志
    log_lines = read_recent_logs(args.hours)

    if not log_lines:
        print("⚠️ 没有新的对话记录，任务结束")
        return

    # 提取客户信息
    customers = extract_customer_info(log_lines)

    if not customers:
        print("⚠️ 未找到客户消息，任务结束")
        return

    print(f"👥 找到 {len(customers)} 个客户的对话记录\n")

    # 更新每个客户的画像
    updated_count = 0
    for nickname, info in customers.items():
        print(f"📊 处理客户: {nickname}")
        print(f"   消息数量: {info['message_count']}")

        # 分析客户意向
        analysis = analyze_customer_intent(info["messages"])
        print(f"   意向度: {analysis['intention']}")
        print(f"   提及产品: {', '.join(analysis['products']) if analysis['products'] else '无'}")

        # 加载现有画像
        profile, profile_path = load_customer_profile(nickname)

        if profile is None:
            print(f"   📝 创建新客户画像")
            profile = create_default_profile(nickname)

        # 更新画像
        profile = update_profile_with_analysis(
            profile,
            analysis,
            info["messages"],
            nickname
        )

        # 保存画像
        if save_customer_profile(profile, profile_path):
            updated_count += 1

        print()

    print(f"✅ 任务完成！共更新 {updated_count} 个客户画像")

if __name__ == "__main__":
    main()
