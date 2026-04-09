#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证飞书配置"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = 'cli_a93fb4f24f785bc3'
APP_SECRET = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'
WEBHOOK_URL = 'https://www.codebuddy.cn/v2/backgroundagent/feishuProxy/webhook/cli_a93fb4f24f785bc3'

# 获取 tenant_token
url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
data = {'app_id': APP_ID, 'app_secret': APP_SECRET}
req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})

with urllib.request.urlopen(req, timeout=10) as resp:
    result = json.loads(resp.read())
    token = result['tenant_access_token']

# 获取机器人信息
url2 = 'https://open.feishu.cn/open-apis/bot/v3/info'
req2 = urllib.request.Request(url2, headers={'Authorization': f'Bearer {token}'})
with urllib.request.urlopen(req2, timeout=10) as resp2:
    bot_info = json.loads(resp2.read())
    bot = bot_info['bot']
    print('=' * 60)
    print('飞书通道配置验证')
    print('=' * 60)
    print('机器人名称:', bot['app_name'])
    print('Open ID:', bot['open_id'])
    print(f'状态: 已激活')
    print()
    print('Webhook URL:')
    print(f'  {WEBHOOK_URL}')
    print()
    print('=' * 60)
    print('配置完成！')
    print('=' * 60)
    print()
    print('现在你可以：')
    print('1. 在飞书中搜索「小龙虾助手」')
    print('2. 给机器人发送消息')
    print('3. 机器人会通过 WorkBuddy 回复你')
