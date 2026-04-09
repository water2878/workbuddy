#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取飞书群聊消息内容
"""

import subprocess
import json
import os
from datetime import datetime, timedelta

def run_command(cmd):
    """运行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=True,
            cwd="C:/Users/Lenovo/WorkBuddy/Claw",
            timeout=60,
            encoding='utf-8'
        )
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1

def get_messages(chat_id, chat_name):
    """获取指定群聊的消息"""
    params = json.dumps({
        "container_id_type": "chat_id",
        "container_id": chat_id,
        "page_size": 20
    })
    
    # 使用 PowerShell 执行
    ps_cmd = f'& npx -y @larksuite/cli api GET /open-apis/im/v1/messages --params \'{params}\' --as user 2>&1'
    cmd = f'powershell -Command "{ps_cmd}"'
    
    print(f"\n[获取] {chat_name} 的消息...")
    stdout, stderr, rc = run_command(cmd)
    
    # 解析结果
    try:
        # 找到 JSON 部分
        lines = stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and line.startswith('{'):
                data = json.loads(line)
                if data.get('ok') and 'data' in data:
                    items = data['data'].get('items', [])
                    return items
                elif data.get('error'):
                    print(f"[API错误] {data['error']}")
                    return None
        return []
    except Exception as e:
        print(f"[解析错误] {e}")
        print(f"[原始输出] {stdout[:500]}")
        return None

def main():
    print("=" * 60)
    print("获取飞书聊天消息内容")
    print("=" * 60)
    
    yesterday = datetime.now() - timedelta(days=1)
    print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
    
    # 要获取消息的群聊
    chats = [
        {"name": "哈哈哈哈哈哈哈", "id": "oc_0170529c7f11a6faa43785a6910d4cf1"},
    ]
    
    all_messages = []
    
    for chat in chats:
        messages = get_messages(chat['id'], chat['name'])
        if messages is not None:
            print(f"[成功] 获取到 {len(messages)} 条消息")
            for msg in messages:
                msg['chat_name'] = chat['name']
            all_messages.extend(messages)
        else:
            print(f"[失败] 无法获取消息")
    
    # 生成报告
    print("\n" + "=" * 60)
    print("消息内容报告")
    print("=" * 60)
    
    if all_messages:
        print(f"\n共 {len(all_messages)} 条消息\n")
        for i, msg in enumerate(all_messages[:10], 1):  # 显示前10条
            msg_type = msg.get('msg_type', 'unknown')
            sender = msg.get('sender', {}).get('sender_id', {}).get('open_id', 'unknown')[:20]
            content = msg.get('body', {}).get('content', '')
            create_time = msg.get('create_time', '')
            
            # 简化显示
            if len(content) > 100:
                content = content[:100] + "..."
            
            print(f"{i}. [{msg_type}] {sender}")
            print(f"   时间: {create_time}")
            print(f"   内容: {content}")
            print()
    else:
        print("\n[提示] 未能获取消息内容")
        print("\n可能的原因：")
        print("1. 应用没有 im:message:readonly 权限")
        print("2. 用户没有授权应用访问消息")
        print("3. 飞书租户管理员限制了消息访问")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
