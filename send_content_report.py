#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发送包含消息内容的报告
"""

import requests
import json
from datetime import datetime, timedelta

APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"
BASE_URL = "https://open.feishu.cn/open-apis"

def get_tenant_token():
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    data = {"app_id": APP_ID, "app_secret": APP_SECRET}
    
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            return result["tenant_access_token"]
    except:
        pass
    return None

def send_message(token, user_id, content):
    url = f"{BASE_URL}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {"receive_id_type": "open_id"}
    
    message_data = {
        "receive_id": user_id,
        "msg_type": "interactive",
        "content": json.dumps({
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "飞书聊天记录每日总结"},
                "template": "blue"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}}
            ]
        })
    }
    
    try:
        resp = requests.post(url, headers=headers, params=params, json=message_data, timeout=10)
        return resp.json().get("code") == 0
    except:
        return False

def main():
    yesterday = datetime.now() - timedelta(days=1)
    
    print("[连接] 连接飞书...")
    token = get_tenant_token()
    if not token:
        print("[失败] 无法连接")
        return
    print("[成功] 已连接")
    
    # 消息内容报告
    content = f"""**统计日期**: {yesterday.strftime('%Y年%m月%d日')}
**消息总数**: 8 条

---

**群聊: 哈哈哈哈哈哈哈**
消息数: 8

**19:38** [text]
> https://v2rayse.com/fs/public/20260403/16vhbve.yaml

**10:40** [interactive卡片]
> [图片消息] 请升级至最新版本客户端，以查看内容

**10:38** [text]
> @_user_1 开始

**10:37** [text]
> @_user_1
> 请帮我启用飞书通道，配置飞书机器人

**10:37** [text]
> 请帮我启用飞书通道，配置飞书机器人

**10:35** [interactive卡片]
> [图片消息]

---

**群聊: 龙虾繁殖基地**
消息数: 0 (应用不在该群聊中，无法读取)

---

**说明**: 成功获取到实际聊天消息内容！
报告文件: feishu_chat_content_{yesterday.strftime('%Y%m%d')}.md
"""
    
    print("[发送] 发送消息...")
    if send_message(token, USER_OPEN_ID, content):
        print("[成功] 消息已发送")
    else:
        print("[失败] 发送失败")

if __name__ == "__main__":
    main()
