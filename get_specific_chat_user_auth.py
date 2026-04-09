#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用用户权限获取指定 chat_id 的昨天聊天记录
"""

import requests
import json
from datetime import datetime, timedelta

# 尝试多个 user_access_token
USER_TOKENS = [
    "u-dZkHKjpYt45X7NfsPOyovq0gmYRwh5ijo2Ga6M002e6.",
    "u-fJY3wXf1BarbFBKlEqE21v5k3W_B15gPPE2aUBM02e69",
]

USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"
BASE_URL = "https://open.feishu.cn/open-apis"

# 指定的 chat_id
TARGET_CHAT_ID = "oc_d9e39d842488bad6ad9a45c6f31508d4"

def get_valid_token():
    """获取有效的 user_access_token"""
    for token in USER_TOKENS:
        # 测试 token 是否有效
        url = f"{BASE_URL}/contact/v3/users/me"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            result = resp.json()
            if result.get("code") == 0:
                print(f"[成功] 找到有效 token")
                return token, result.get("data", {})
        except:
            pass
    return None, None

def get_chat_messages(token, start_ts, end_ts):
    """获取聊天消息（用户权限）"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "container_id_type": "chat",
        "container_id": TARGET_CHAT_ID,
        "start_time": start_ts,
        "end_time": end_ts,
        "page_size": 50
    }
    
    all_msgs = []
    page_token = ""
    
    while True:
        if page_token:
            params["page_token"] = page_token
        
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        result = resp.json()
        
        if result.get("code") != 0:
            print(f"  [错误] {result.get('msg')}")
            return None
        
        items = result.get("data", {}).get("items", [])
        all_msgs.extend(items)
        
        has_more = result.get("data", {}).get("has_more", False)
        if not has_more:
            break
        page_token = result.get("data", {}).get("page_token", "")
    
    return all_msgs

def format_message(msg, my_open_id=None):
    """格式化消息内容"""
    msg_type = msg.get("msg_type", "unknown")
    content = msg.get("body", {}).get("content", "")
    create_time = msg.get("create_time", "")
    sender = msg.get("sender", {})
    sender_id = sender.get("sender_id", {}).get("open_id", "")
    
    # 解析时间
    if create_time:
        try:
            dt = datetime.fromtimestamp(int(create_time) / 1000)
            time_str = dt.strftime("%m-%d %H:%M")
        except:
            time_str = str(create_time)
    else:
        time_str = "未知"
    
    # 判断发送者
    if sender_id == my_open_id:
        sender_name = "我"
    elif sender_id:
        sender_name = sender_id[:10]
    else:
        sender_name = "未知"
    
    # 解析内容
    try:
        content_obj = json.loads(content)
        if isinstance(content_obj, dict):
            if "text" in content_obj:
                text = content_obj["text"]
            elif msg_type == "image":
                text = "[图片]"
            elif msg_type == "file":
                text = "[文件]"
            elif msg_type == "post":
                text = "[富文本消息]"
            else:
                text = str(content_obj)[:100]
        else:
            text = str(content)[:100]
    except:
        text = str(content)[:100] if content else "[无内容]"
    
    return time_str, sender_name, msg_type, text

def send_message_to_user(token, user_id, content):
    """发送消息给用户"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    max_length = 4900
    
    if len(content) <= max_length:
        chunks = [content]
    else:
        chunks = []
        while content:
            if len(content) <= max_length:
                chunks.append(content)
                break
            split_pos = content.rfind('\n', 0, max_length)
            if split_pos == -1:
                split_pos = max_length
            chunks.append(content[:split_pos])
            content = content[split_pos:].lstrip()
    
    success = True
    for i, chunk in enumerate(chunks):
        if i < len(chunks) - 1:
            chunk = chunk + "\n\n...(消息继续)..."
        
        data = {
            "receive_id": user_id,
            "msg_type": "text",
            "content": json.dumps({"text": chunk})
        }
        
        params = {"receive_id_type": "open_id"}
        
        try:
            resp = requests.post(url, headers=headers, params=params, json=data, timeout=10)
            result = resp.json()
            if result.get("code") != 0:
                print(f"  [错误] 发送失败: {result.get('msg')}")
                success = False
        except Exception as e:
            print(f"  [错误] 发送请求失败: {e}")
            success = False
    
    return success

def main():
    print("=" * 70)
    print(f"获取指定 chat 的聊天记录 (用户权限)")
    print(f"chat_id: {TARGET_CHAT_ID}")
    print("=" * 70)
    
    # 计算昨天的时间范围
    yesterday = datetime.now() - timedelta(days=1)
    start_ts = int(yesterday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    end_ts = int(yesterday.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())
    
    date_str = yesterday.strftime('%Y年%m月%d日')
    print(f"\n[日期] {date_str}")
    
    # 获取有效的 user_access_token
    print("\n[验证] 查找有效的 user_access_token...")
    token, user_info = get_valid_token()
    if not token:
        print("[失败] 没有找到有效的 user_access_token")
        print("[提示] 需要重新获取 user_access_token")
        return
    
    my_name = user_info.get("name", "Unknown")
    my_open_id = user_info.get("open_id", "")
    print(f"[成功] 当前用户: {my_name}")
    
    # 获取消息
    print(f"\n[获取] 聊天记录...")
    msgs = get_chat_messages(token, start_ts, end_ts)
    
    if msgs is None:
        print("[失败] 无法获取消息")
        return
    
    print(f"[成功] 共 {len(msgs)} 条消息")
    
    # 生成报告
    report_lines = [
        f"📋 聊天记录详情 ({date_str}) - 用户权限获取",
        "",
        f"👤 用户: {my_name}",
        f"🔑 chat_id: {TARGET_CHAT_ID}",
        f"📊 消息数: {len(msgs)} 条",
        "",
        "=" * 50,
        ""
    ]
    
    if msgs:
        # 按时间排序
        msgs_sorted = sorted(msgs, key=lambda x: x.get("create_time", ""))
        
        for msg in msgs_sorted:
            time_str, sender, msg_type, text = format_message(msg, my_open_id)
            report_lines.append(f"[{time_str}] {sender} ({msg_type}):")
            report_lines.append(f"  {text}")
            report_lines.append("")
    else:
        report_lines.append("该聊天昨日无消息。")
    
    report = "\n".join(report_lines)
    
    # 保存报告到文件
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/chat_{TARGET_CHAT_ID[-12:]}_{yesterday.strftime('%Y%m%d')}_user.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n[完成] 报告已保存: {report_file}")
    
    # 发送到飞书
    print("\n[发送] 发送报告到飞书...")
    if send_message_to_user(token, USER_OPEN_ID, report):
        print("[成功] 消息已发送!")
    else:
        print("[失败] 发送消息时出现问题")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
