#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证飞书应用配置"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = 'cli_a93fb4f24f785bc3'
APP_SECRET = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'

# 获取 tenant_access_token
url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
data = {'app_id': APP_ID, 'app_secret': APP_SECRET}
req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        if result.get('code') == 0:
            print('✅ App ID 和 App Secret 有效')
            token = result['tenant_access_token']
            print(f'Tenant Token: {token[:30]}...')
            
            # 获取机器人信息
            url2 = 'https://open.feishu.cn/open-apis/bot/v3/info'
            req2 = urllib.request.Request(url2, headers={'Authorization': f'Bearer {token}'})
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                bot_info = json.loads(resp2.read())
                if bot_info.get('code') == 0:
                    bot = bot_info['bot']
                    print(f"\n🤖 机器人信息:")
                    print(f"  名称: {bot['app_name']}")
                    print(f"  Open ID: {bot['open_id']}")
                    print(f"  状态: {'已激活' if bot['activate_status'] == 2 else '未激活'}")
        else:
            print(f"❌ 错误: {result.get('msg')}")
except Exception as e:
    print(f"❌ 请求失败: {e}")
