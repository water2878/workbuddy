#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置飞书事件订阅"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = 'cli_a93fb4f24f785bc3'
APP_SECRET = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'
WEBHOOK_URL = 'https://www.codebuddy.cn/v2/backgroundagent/feishuProxy/webhook/cli_a93fb4f24f785bc3'

def get_tenant_token():
    """获取 tenant_access_token"""
    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    data = {'app_id': APP_ID, 'app_secret': APP_SECRET}
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        return result.get('tenant_access_token')

def update_event_subscription(token):
    """更新事件订阅配置"""
    url = 'https://open.feishu.cn/open-apis/event-subscription/v2/subscription'
    
    data = {
        'subscription': {
            'url': WEBHOOK_URL,
            'events': [
                {
                    'event_type': 'im.message.receive_v1',
                    'verify_token': ''
                }
            ]
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        },
        method='PUT'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def get_subscription(token):
    """获取当前事件订阅配置"""
    url = 'https://open.feishu.cn/open-apis/event-subscription/v2/subscription'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def main():
    print("=" * 60)
    print("配置飞书事件订阅")
    print("=" * 60)
    
    # 获取 token
    token = get_tenant_token()
    print(f"\n1. 获取 Tenant Token: {token[:30]}...")
    
    # 获取当前配置
    print("\n2. 获取当前事件订阅配置...")
    current = get_subscription(token)
    print(f"   当前配置: {json.dumps(current, indent=2, ensure_ascii=False)[:500]}")
    
    # 更新配置
    print("\n3. 更新事件订阅配置...")
    print(f"   Webhook URL: {WEBHOOK_URL}")
    result = update_event_subscription(token)
    print(f"   结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if result.get('code') == 0:
        print("\n✅ 事件订阅配置成功！")
    else:
        print(f"\n❌ 配置失败: {result.get('msg')}")
        print("\n请手动配置：")
        print("1. 访问 https://open.feishu.cn/app/cli_a93fb4f24f785bc3/event")
        print("2. 在「事件订阅」中填入 Webhook URL:")
        print(f"   {WEBHOOK_URL}")
        print("3. 添加事件：接收消息 (im.message.receive_v1)")

if __name__ == "__main__":
    main()
