#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取飞书群聊消息内容
"""

import requests
import json
import time
from datetime import datetime, timedelta

APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"

def get_tenant_token():
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    data = {"app_id": APP_ID, "app_secret": APP_SECRET}
    
    resp = requests.post(url, headers=headers, json=data, timeout=10)
    result = resp.json()
    if result.get("code") == 0:
        return result["tenant_access_token"]
    return None

def get_messages(token, chat_id, start_ts, end_ts):
    """获取指定时间段的消息"""
    base_url = "https://open.feishu.cn/open-apis/im/v1/messages"
    
    all_messages = []
    page_token = ""
    has_more = True
    
    while has_more:
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "start_time": start_ts,
            "end_time": end_ts,
            "sort_type": "ByCreateTimeDesc",
            "page_size": 50
        }
        if page_token:
            params["page_token"] = page_token
        
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(base_url, headers=headers, params=params, timeout=10)
        result = resp.json()
        
        if result.get("code") != 0:
            print(f"[API错误] {result}")
            return None
        
        items = result.get("data", {}).get("items", [])
        all_messages.extend(items)
        
        has_more = result.get("data", {}).get("has_more", False)
        page_token = result.get("data", {}).get("page_token", "")
        
        if not page_token:
            has_more = False
    
    return all_messages

def format_message(msg):
    """格式化消息"""
    msg_type = msg.get("msg_type", "unknown")
    sender = msg.get("sender", {})
    sender_type = sender.get("sender_type", "unknown")
    sender_id = sender.get("sender_id", {}).get("open_id", "unknown")[:15]
    body = msg.get("body", {})
    content = body.get("content", "")
    create_time = msg.get("create_time", 0)
    
    # 解析时间
    if create_time:
        dt = datetime.fromtimestamp(int(create_time) / 1000)
        time_str = dt.strftime("%H:%M")
    else:
        time_str = "未知"
    
    # 解析内容
    try:
        content_obj = json.loads(content)
        if isinstance(content_obj, dict):
            if "text" in content_obj:
                content = content_obj["text"]
    except:
        pass
    
    # 截断长内容
    if len(content) > 150:
        content = content[:150] + "..."
    
    return {
        "time": time_str,
        "sender": sender_id,
        "type": msg_type,
        "content": content
    }

def main():
    print("=" * 70)
    print("飞书聊天记录每日总结 - 获取消息内容")
    print("=" * 70)
    
    yesterday = datetime.now() - timedelta(days=1)
    start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    start_ts = int(start_of_day.timestamp())
    end_ts = int(end_of_day.timestamp())
    
    print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
    print(f"[时间戳] {start_ts} ~ {end_ts}")
    
    # 获取 token
    print("\n[连接] 获取访问令牌...")
    token = get_tenant_token()
    if not token:
        print("[失败] 无法获取令牌")
        return
    print("[成功] 已获取令牌")
    
    # 要查询的群聊
    chats = [
        {"name": "哈哈哈哈哈哈哈", "id": "oc_0170529c7f11a6faa43785a6910d4cf1"},
        {"name": "龙虾繁殖基地", "id": "oc_47ec374827424133a4f739ab7f576454"},
    ]
    
    all_messages = []
    
    for chat in chats:
        print(f"\n[获取] {chat['name']}...")
        messages = get_messages(token, chat['id'], start_ts, end_ts)
        
        if messages is None:
            print(f"[失败] 获取消息失败")
            continue
        
        print(f"[成功] 获取到 {len(messages)} 条消息")
        
        for msg in messages:
            msg['chat_name'] = chat['name']
        all_messages.extend(messages)
    
    # 生成报告
    print("\n" + "=" * 70)
    print("生成报告")
    print("=" * 70)
    
    if all_messages:
        print(f"\n总计: {len(all_messages)} 条消息\n")
        
        # 按时间排序
        all_messages.sort(key=lambda x: x.get('create_time', 0), reverse=True)
        
        # 生成报告内容
        report_lines = [
            "# 飞书聊天记录每日总结",
            "",
            f"**统计日期**: {yesterday.strftime('%Y年%m月%d日')}",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**消息总数**: {len(all_messages)}",
            "",
            "---",
            "",
        ]
        
        # 按群聊分组
        for chat in chats:
            chat_messages = [m for m in all_messages if m.get('chat_name') == chat['name']]
            if chat_messages:
                report_lines.extend([
                    f"## {chat['name']}",
                    f"消息数: {len(chat_messages)}",
                    "",
                ])
                
                for msg in chat_messages[:20]:  # 每个群聊最多20条
                    formatted = format_message(msg)
                    report_lines.append(f"**{formatted['time']}** [{formatted['type']}] {formatted['sender']}")
                    report_lines.append(f"> {formatted['content']}")
                    report_lines.append("")
        
        report = '\n'.join(report_lines)
        
        # 保存报告
        report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_chat_content_{yesterday.strftime('%Y%m%d')}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n[完成] 报告已保存: {report_file}")
        
        # 显示预览
        print("\n报告预览:")
        print("-" * 70)
        print(report[:2000])
        print("...")
    else:
        print("\n[提示] 未获取到任何消息")
        print("\n可能原因:")
        print("1. 昨天这些群聊没有新消息")
        print("2. 应用需要添加到群聊中才能读取消息")
        print("3. 飞书管理员限制了消息访问权限")
    
    print("=" * 70)

if __name__ == "__main__":
    main()
