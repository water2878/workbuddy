#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取昨天的所有飞书聊天记录（群聊+单聊）并发送给用户
自动遍历获取所有 chat_id
"""

import requests
import json
from datetime import datetime, timedelta

# 飞书配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"

BASE_URL = "https://open.feishu.cn/open-apis"

def get_tenant_token():
    """获取 tenant_access_token"""
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    return resp.json().get("tenant_access_token")

def get_all_chats(token, chat_type=None):
    """获取所有会话（群聊或单聊）"""
    url = f"{BASE_URL}/im/v1/chats"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"page_size": 100}
    
    # 如果指定了 chat_type，添加过滤
    if chat_type:
        params["chat_type"] = chat_type  # 'group' 或 'p2p'
    
    all_chats = []
    page_token = ""
    
    while True:
        if page_token:
            params["page_token"] = page_token
        
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        result = resp.json()
        
        if result.get("code") != 0:
            print(f"  [错误] 获取会话列表失败: {result.get('msg')}")
            break
        
        items = result.get("data", {}).get("items", [])
        all_chats.extend(items)
        
        if not result.get("data", {}).get("has_more"):
            break
        page_token = result.get("data", {}).get("page_token", "")
    
    return all_chats

def get_chat_messages(token, chat_id, start_ts, end_ts, container_type="chat"):
    """获取聊天消息"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "container_id_type": container_type,  # 'chat' 或 'open_id'
        "container_id": chat_id,
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
        
        if not result.get("data", {}).get("has_more"):
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
            time_str = dt.strftime("%H:%M")
        except:
            time_str = str(create_time)[:5]
    else:
        time_str = "未知"
    
    # 判断发送者
    if sender_id == my_open_id:
        sender_name = "我"
    elif sender_id:
        sender_name = sender_id[:12]
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
    
    # 截断过长的文本
    if len(text) > 200:
        text = text[:200] + "..."
    
    return time_str, sender_name, msg_type, text

def send_message_to_user(token, user_id, content):
    """发送消息给用户"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 如果内容太长，分段发送
    max_length = 4900  # 飞书消息长度限制
    
    if len(content) <= max_length:
        chunks = [content]
    else:
        chunks = []
        while content:
            if len(content) <= max_length:
                chunks.append(content)
                break
            # 找到最后一个换行符
            split_pos = content.rfind('\n', 0, max_length)
            if split_pos == -1:
                split_pos = max_length
            chunks.append(content[:split_pos])
            content = content[split_pos:].lstrip()
    
    success = True
    for i, chunk in enumerate(chunks):
        # 如果不是最后一块，添加续接标记
        if i < len(chunks) - 1:
            chunk = chunk + "\n\n...(消息继续)..."
        
        message_data = {
            "receive_id": user_id,
            "msg_type": "text",
            "content": json.dumps({"text": chunk})
        }
        
        params = {"receive_id_type": "open_id"}
        
        try:
            resp = requests.post(url, headers=headers, params=params, json=message_data, timeout=10)
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
    print("获取昨天的飞书聊天记录并发送")
    print("=" * 70)
    
    # 计算昨天的时间范围
    yesterday = datetime.now() - timedelta(days=1)
    start_ts = int(yesterday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    end_ts = int(yesterday.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())
    
    date_str = yesterday.strftime('%Y年%m月%d日')
    print(f"\n[日期] {date_str}")
    print(f"[时间范围] {datetime.fromtimestamp(start_ts)} ~ {datetime.fromtimestamp(end_ts)}")
    
    # 获取 token
    print("\n[连接] 获取访问令牌...")
    token = get_tenant_token()
    if not token:
        print("[失败] 无法获取令牌")
        return
    print("[成功] 已获取令牌")
    
    all_messages = []
    group_chats_with_messages = []
    single_chats_with_messages = []
    
    # ========== 1. 获取所有群聊消息 ==========
    print("\n" + "-" * 70)
    print("[步骤1] 获取所有群聊消息")
    print("-" * 70)
    
    group_chats = get_all_chats(token, chat_type="group")
    print(f"[信息] 共找到 {len(group_chats)} 个群聊")
    
    for chat in group_chats:
        chat_id = chat.get("chat_id")
        chat_name = chat.get("name") or "(未命名群聊)"
        
        msgs = get_chat_messages(token, chat_id, start_ts, end_ts, container_type="chat")
        if msgs is not None:
            msg_count = len(msgs)
            if msg_count > 0:
                print(f"  [群聊] {chat_name}: {msg_count} 条消息")
                group_chats_with_messages.append({
                    "chat": chat,
                    "messages": msgs
                })
                for msg in msgs:
                    msg["_chat_type"] = "group"
                    msg["_chat_name"] = chat_name
                    all_messages.append(msg)
            else:
                print(f"  [群聊] {chat_name}: 无消息")
    
    # ========== 2. 获取所有单聊消息 ==========
    print("\n" + "-" * 70)
    print("[步骤2] 获取所有单聊消息")
    print("-" * 70)
    
    # 方法1: 通过 chat_type=p2p 获取单聊会话列表
    p2p_chats = get_all_chats(token, chat_type="p2p")
    print(f"[信息] 通过 chat_type=p2p 找到 {len(p2p_chats)} 个单聊会话")
    
    for chat in p2p_chats:
        chat_id = chat.get("chat_id")
        chat_name = chat.get("name") or f"单聊-{chat_id[:20]}"
        
        # 单聊使用 chat_id 获取消息
        msgs = get_chat_messages(token, chat_id, start_ts, end_ts, container_type="chat")
        if msgs is not None:
            msg_count = len(msgs)
            if msg_count > 0:
                print(f"  [单聊] {chat_name}: {msg_count} 条消息")
                single_chats_with_messages.append({
                    "chat": chat,
                    "messages": msgs
                })
                for msg in msgs:
                    msg["_chat_type"] = "single"
                    msg["_chat_name"] = chat_name
                    all_messages.append(msg)
            else:
                print(f"  [单聊] {chat_name}: 无消息")
    
    # 方法2: 尝试通过 open_id 获取（从群聊成员中提取）
    if not single_chats_with_messages:
        print("\n[步骤2b] 尝试从群聊成员获取单聊...")
        sender_ids = set()
        for msg in all_messages:
            sender = msg.get("sender", {})
            sender_id = sender.get("sender_id", {}).get("open_id", "")
            # 排除自己
            if sender_id and sender_id != USER_OPEN_ID:
                sender_ids.add(sender_id)
        
        print(f"[信息] 从群聊中发现 {len(sender_ids)} 个联系人")
        
        for sender_id in sender_ids:
            msgs = get_chat_messages(token, sender_id, start_ts, end_ts, container_type="open_id")
            if msgs is not None and len(msgs) > 0:
                print(f"  [单聊] {sender_id[:30]}...: {len(msgs)} 条消息")
                single_chats_with_messages.append({
                    "user_id": sender_id,
                    "messages": msgs
                })
                for msg in msgs:
                    msg["_chat_type"] = "single"
                    msg["_chat_name"] = f"单聊-{sender_id[:20]}"
                    all_messages.append(msg)
    
    # ========== 3. 生成报告 ==========
    print("\n" + "=" * 70)
    print("[步骤3] 生成聊天记录报告")
    print("=" * 70)
    
    group_count = len(group_chats_with_messages)
    single_count = len(single_chats_with_messages)
    total_messages = len(all_messages)
    
    report_lines = [
        f"📋 飞书聊天记录日报 ({date_str})",
        "",
        f"📊 统计概览:",
        f"   • 活跃群聊: {group_count} 个",
        f"   • 活跃单聊: {single_count} 个",
        f"   • 总消息数: {total_messages} 条",
        "",
        "=" * 50,
        ""
    ]
    
    # 群聊消息
    if group_chats_with_messages:
        report_lines.append("📢 群聊消息:")
        report_lines.append("")
        
        for chat_data in group_chats_with_messages:
            chat_name = chat_data["chat"].get("name") or "(未命名群聊)"
            msgs = chat_data["messages"]
            chat_id = chat_data["chat"].get("chat_id", "")
            report_lines.append(f"【{chat_name}】")
            report_lines.append(f"  chat_id: {chat_id}")
            report_lines.append(f"  消息数: {len(msgs)} 条")
            report_lines.append("")
            
            # 按时间排序
            msgs_sorted = sorted(msgs, key=lambda x: x.get("create_time", ""))
            
            for msg in msgs_sorted[:25]:  # 每个群聊最多显示25条
                time_str, sender, msg_type, text = format_message(msg, USER_OPEN_ID)
                report_lines.append(f"  [{time_str}] {sender}: {text}")
            
            if len(msgs_sorted) > 25:
                report_lines.append(f"  ... 还有 {len(msgs_sorted) - 25} 条消息未显示")
            
            report_lines.append("")
    
    # 单聊消息
    if single_chats_with_messages:
        report_lines.append("💬 单聊消息:")
        report_lines.append("")
        
        for chat_data in single_chats_with_messages:
            if "chat" in chat_data:
                chat_name = chat_data["chat"].get("name") or "(单聊)"
                chat_id = chat_data["chat"].get("chat_id", "")
            else:
                chat_name = f"单聊-{chat_data.get('user_id', '未知')[:20]}"
                chat_id = chat_data.get("user_id", "")
            
            msgs = chat_data["messages"]
            report_lines.append(f"【{chat_name}】")
            report_lines.append(f"  chat_id/open_id: {chat_id}")
            report_lines.append(f"  消息数: {len(msgs)} 条")
            report_lines.append("")
            
            # 按时间排序
            msgs_sorted = sorted(msgs, key=lambda x: x.get("create_time", ""))
            
            for msg in msgs_sorted[:20]:  # 每个单聊最多显示20条
                time_str, sender, msg_type, text = format_message(msg, USER_OPEN_ID)
                report_lines.append(f"  [{time_str}] {sender}: {text}")
            
            if len(msgs_sorted) > 20:
                report_lines.append(f"  ... 还有 {len(msgs_sorted) - 20} 条消息未显示")
            
            report_lines.append("")
    
    if not group_chats_with_messages and not single_chats_with_messages:
        report_lines.append("昨天没有新的聊天记录。")
    
    report = "\n".join(report_lines)
    
    # 保存报告到文件
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/chat_report_{yesterday.strftime('%Y%m%d')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n[完成] 报告已保存: {report_file}")
    
    # ========== 4. 发送到飞书 ==========
    print("\n" + "=" * 70)
    print("[步骤4] 发送报告到飞书")
    print("=" * 70)
    
    print(f"[发送] 正在发送给 {USER_OPEN_ID[:30]}...")
    if send_message_to_user(token, USER_OPEN_ID, report):
        print("[成功] 消息已发送!")
    else:
        print("[失败] 发送消息时出现问题")
    
    print("\n" + "=" * 70)
    print("任务完成!")
    print("=" * 70)

if __name__ == "__main__":
    main()
