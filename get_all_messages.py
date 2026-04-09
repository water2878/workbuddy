#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取飞书所有聊天记录（群聊 + 单聊）
"""

import requests
import json
from datetime import datetime, timedelta

APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"

def get_tenant_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    return resp.json().get("tenant_access_token")

def get_chat_messages(token, chat_id, start_ts, end_ts):
    """获取群聊消息"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    params = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "start_time": start_ts,
        "end_time": end_ts,
        "page_size": 50
    }
    headers = {"Authorization": f"Bearer {token}"}
    
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
        
        if not result.get("data", {}).get("has_more"):
            break
        page_token = result.get("data", {}).get("page_token", "")
    
    return all_msgs

def get_single_chat_messages(token, user_id, start_ts, end_ts):
    """获取单聊消息 - 使用 open_id 作为 container_id"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    params = {
        "container_id_type": "open_id",  # 单聊使用 open_id
        "container_id": user_id,
        "start_time": start_ts,
        "end_time": end_ts,
        "page_size": 50
    }
    headers = {"Authorization": f"Bearer {token}"}
    
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
        
        if not result.get("data", {}).get("has_more"):
            break
        page_token = result.get("data", {}).get("page_token", "")
    
    return all_msgs

def format_msg(msg):
    """格式化消息"""
    msg_type = msg.get("msg_type", "unknown")
    body = msg.get("body", {})
    content = body.get("content", "")
    create_time = msg.get("create_time", 0)
    
    if create_time:
        dt = datetime.fromtimestamp(int(create_time) / 1000)
        time_str = dt.strftime("%H:%M")
    else:
        time_str = "未知"
    
    # 解析内容
    try:
        content_obj = json.loads(content)
        if isinstance(content_obj, dict) and "text" in content_obj:
            content = content_obj["text"]
    except:
        pass
    
    if len(content) > 150:
        content = content[:150] + "..."
    
    return time_str, msg_type, content

def main():
    print("=" * 70)
    print("飞书聊天记录每日总结 - 群聊 + 单聊")
    print("=" * 70)
    
    yesterday = datetime.now() - timedelta(days=1)
    start_ts = int(yesterday.replace(hour=0, minute=0, second=0).timestamp())
    end_ts = int(yesterday.replace(hour=23, minute=59, second=59).timestamp())
    
    print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
    
    print("\n[连接] 获取访问令牌...")
    token = get_tenant_token()
    if not token:
        print("[失败] 无法获取令牌")
        return
    print("[成功] 已获取令牌")
    
    all_messages = []
    
    # 1. 获取群聊消息
    print("\n" + "-" * 70)
    print("[1/2] 获取群聊消息")
    print("-" * 70)
    
    chats = [
        {"name": "哈哈哈哈哈哈哈", "id": "oc_0170529c7f11a6faa43785a6910d4cf1"},
    ]
    
    for chat in chats:
        print(f"\n[群聊] {chat['name']}")
        msgs = get_chat_messages(token, chat['id'], start_ts, end_ts)
        if msgs is not None:
            print(f"  [成功] {len(msgs)} 条消息")
            for msg in msgs:
                msg['chat_type'] = 'group'
                msg['chat_name'] = chat['name']
            all_messages.extend(msgs)
        else:
            print(f"  [失败] 无法获取")
    
    # 2. 获取单聊消息
    print("\n" + "-" * 70)
    print("[2/2] 获取单聊消息")
    print("-" * 70)
    
    # 单聊需要使用对方的 open_id
    # 从群聊消息中提取发送者，尝试获取与他们的单聊
    sender_ids = set()
    for msg in all_messages:
        sender = msg.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        if sender_id and sender_id != "ou_4a86846caf437e8fda2fc9f2794c5424":
            sender_ids.add(sender_id)
    
    print(f"\n[发现] 从群聊中找到 {len(sender_ids)} 个联系人")
    
    single_chat_count = 0
    for sender_id in list(sender_ids)[:5]:  # 最多查5个
        print(f"\n[单聊] 查询与 {sender_id[:20]}... 的消息")
        msgs = get_single_chat_messages(token, sender_id, start_ts, end_ts)
        if msgs is not None:
            print(f"  [成功] {len(msgs)} 条消息")
            for msg in msgs:
                msg['chat_type'] = 'single'
                msg['chat_name'] = f"单聊-{sender_id[:15]}"
            all_messages.extend(msgs)
            single_chat_count += len(msgs)
        else:
            print(f"  [失败] 无法获取")
    
    # 生成报告
    print("\n" + "=" * 70)
    print("生成完整报告")
    print("=" * 70)
    
    group_msgs = [m for m in all_messages if m.get('chat_type') == 'group']
    single_msgs = [m for m in all_messages if m.get('chat_type') == 'single']
    
    print(f"\n[统计]")
    print(f"  群聊消息: {len(group_msgs)} 条")
    print(f"  单聊消息: {len(single_msgs)} 条")
    print(f"  总计: {len(all_messages)} 条")
    
    # 构建报告
    report_lines = [
        "# 飞书聊天记录每日总结",
        "",
        f"**统计日期**: {yesterday.strftime('%Y年%m月%d日')}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## 消息统计",
        "",
        f"| 类型 | 数量 |",
        f"|------|------|",
        f"| 群聊消息 | {len(group_msgs)} |",
        f"| 单聊消息 | {len(single_msgs)} |",
        f"| **总计** | **{len(all_messages)}** |",
        "",
        "---",
        "",
    ]
    
    # 群聊消息
    if group_msgs:
        report_lines.extend([
            "## 群聊消息",
            "",
        ])
        for msg in group_msgs[:15]:
            time_str, msg_type, content = format_msg(msg)
            chat_name = msg.get('chat_name', '未知群聊')
            report_lines.append(f"**{chat_name}** {time_str} [{msg_type}]")
            report_lines.append(f"> {content}")
            report_lines.append("")
    
    # 单聊消息
    if single_msgs:
        report_lines.extend([
            "## 单聊消息",
            "",
        ])
        for msg in single_msgs[:15]:
            time_str, msg_type, content = format_msg(msg)
            sender = msg.get('sender', {}).get('sender_id', {}).get('open_id', 'unknown')[:15]
            report_lines.append(f"**{sender}** {time_str} [{msg_type}]")
            report_lines.append(f"> {content}")
            report_lines.append("")
    
    report = '\n'.join(report_lines)
    
    # 保存报告
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_full_chat_{yesterday.strftime('%Y%m%d')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n[完成] 报告已保存: {report_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()
