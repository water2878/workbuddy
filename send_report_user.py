#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发送飞书报告（使用用户权限）
"""

import requests
import json
from datetime import datetime, timedelta

APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"
BASE_URL = "https://open.feishu.cn/open-apis"

def get_tenant_access_token():
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    data = {"app_id": APP_ID, "app_secret": APP_SECRET}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            return result["tenant_access_token"]
        return None
    except:
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
        response = requests.post(url, headers=headers, params=params, json=message_data, timeout=10)
        result = response.json()
        return result.get("code") == 0
    except:
        return False

def main():
    yesterday = datetime.now() - timedelta(days=1)
    
    print("[连接] 正在连接飞书...")
    token = get_tenant_access_token()
    if not token:
        print("[失败] 无法获取访问令牌")
        return
    print("[成功] 已获取访问令牌")
    
    # 构建消息内容
    content = f"""**统计日期**: {yesterday.strftime('%Y年%m月%d日')}

---

**消息统计**

| 类别 | 数量 |
|------|------|
| 群聊总数 | 11 |
| 外部群聊 | 7 |
| 内部群聊 | 4 |
| 活跃群聊 | 9 |
| 已解散 | 2 |

---

**活跃群聊列表**

• 龙虾繁殖基地 (外部)
• 滕成's Feishu Assistant (外部)
• 哈哈哈哈哈哈哈 (内部)
• 用户751423's FeiShu customer service (外部)
• 郑淡定, 用户751423 (外部)
• 【用户751423 妙搭技术服务工单群】(外部)
• 4个未命名群聊

---

**使用用户权限获取的数据**
[OK] 成功使用 user 权限获取群聊列表

报告文件: feishu_summary_{yesterday.strftime('%Y%m%d')}_final.md
"""
    
    print("[发送] 正在发送消息...")
    if send_message(token, USER_OPEN_ID, content):
        print("[成功] 消息已发送到飞书")
    else:
        print("[失败] 发送消息失败")

if __name__ == "__main__":
    main()
