#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接获取单聊消息
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

def main():
    print("=" * 70)
    print("获取单聊消息")
    print("=" * 70)
    
    yesterday = datetime.now() - timedelta(days=1)
    start_ts = int(yesterday.replace(hour=0, minute=0, second=0).timestamp())
    end_ts = int(yesterday.replace(hour=23, minute=59, second=59).timestamp())
    
    print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
    
    token = get_tenant_token()
    if not token:
        print("[失败] 无法获取令牌")
        return
    print("[成功] 已获取令牌")
    
    # 单聊需要使用对方的 open_id
    # 尝试获取与几个常见联系人的单聊
    # 注意：这里需要知道对方的 open_id
    
    print("\n[说明] 单聊消息需要使用对方的 open_id 作为 container_id")
    print("       飞书 API 没有提供获取单聊列表的接口")
    print("       需要从其他途径获取联系人 open_id")
    
    # 尝试从群聊成员中获取
    print("\n[尝试] 从群聊成员中获取联系人...")
    
    # 先获取群聊成员
    chat_id = "oc_0170529c7f11a6faa43785a6910d4cf1"
    url = f"https://open.feishu.cn/open-apis/chat/v4/members"
    params = {"chat_id": chat_id, "page_size": 100}
    headers = {"Authorization": f"Bearer {token}"}
    
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    result = resp.json()
    
    if result.get("code") == 0:
        members = result.get("data", {}).get("members", [])
        print(f"[成功] 群聊有 {len(members)} 个成员")
        
        for member in members[:5]:
            member_id = member.get("member_id", "")
            member_type = member.get("member_id_type", "")
            print(f"  - {member_type}: {member_id[:30]}...")
            
            # 尝试获取与该成员的单聊
            if member_type == "open_id" and member_id != "ou_4a86846caf437e8fda2fc9f2794c5424":
                print(f"\n  [查询] 与该成员的单聊消息...")
                msg_url = "https://open.feishu.cn/open-apis/im/v1/messages"
                msg_params = {
                    "container_id_type": "open_id",
                    "container_id": member_id,
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "page_size": 20
                }
                
                msg_resp = requests.get(msg_url, headers=headers, params=msg_params, timeout=10)
                msg_result = msg_resp.json()
                
                if msg_result.get("code") == 0:
                    items = msg_result.get("data", {}).get("items", [])
                    print(f"  [成功] {len(items)} 条消息")
                else:
                    print(f"  [失败] {msg_result.get('msg', '未知错误')}")
    else:
        print(f"[失败] 无法获取群成员: {result.get('msg')}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
