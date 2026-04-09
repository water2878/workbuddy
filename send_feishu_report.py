#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发送飞书聊天记录总结报告
"""

import requests
import json
from datetime import datetime, timedelta

# 飞书配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"

BASE_URL = "https://open.feishu.cn/open-apis"

def get_tenant_access_token():
    """获取 tenant_access_token"""
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    data = {
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            return result["tenant_access_token"]
        else:
            print(f"[错误] 获取 token 失败: {result}")
            return None
    except Exception as e:
        print(f"[错误] 请求失败: {e}")
        return None

def send_message(token, user_id, content):
    """发送消息给用户"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 构建消息内容
    params = {
        "receive_id_type": "open_id"
    }
    
    message_data = {
        "receive_id": user_id,
        "msg_type": "interactive",
        "content": json.dumps({
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "📊 飞书聊天记录每日总结"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                }
            ]
        })
    }
    
    try:
        response = requests.post(url, headers=headers, params=params, json=message_data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            print("[成功] 消息已发送")
            return True
        else:
            print(f"[错误] 发送失败: {result}")
            return False
    except Exception as e:
        print(f"[错误] 请求失败: {e}")
        return False

def main():
    print("=" * 60)
    print("发送飞书聊天记录总结")
    print("=" * 60)
    
    yesterday = datetime.now() - timedelta(days=1)
    
    # 获取访问令牌
    print("\n[连接] 正在连接飞书 API...")
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
| 群聊数量 | 3 |
| 单聊消息 | 需要 user_access_token |

---

**群聊列表**

• 哈哈哈哈哈哈哈
• (2个未命名群聊)

---

**说明**: 每日总结自动化任务已执行完成。
报告文件: `feishu_summary_{yesterday.strftime('%Y%m%d')}.md`
"""
    
    # 发送消息
    print("\n[发送] 正在发送消息...")
    if send_message(token, USER_OPEN_ID, content):
        print("[完成] 消息已发送到飞书")
    else:
        print("[失败] 发送消息失败")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
