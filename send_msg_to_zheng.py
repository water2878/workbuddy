#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给郑淡定发送消息"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = 'cli_a93fb4f24f785bc3'
APP_SECRET = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'
ZHENG_OPEN_ID = 'ou_12d9689fa81e05ed626f98734cebacc7'

def get_tenant_token():
    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    data = {'app_id': APP_ID, 'app_secret': APP_SECRET}
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        return result['tenant_access_token']

def send_message(token, user_id, content):
    """发送消息给用户"""
    url = 'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id'
    
    data = {
        'receive_id': user_id,
        'content': json.dumps({'text': content}),
        'msg_type': 'text'
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def main():
    print('=' * 60)
    print('给郑淡定发送消息')
    print('=' * 60)
    
    token = get_tenant_token()
    print('\n1. 获取 Tenant Token 成功')
    
    print('\n2. 发送消息给郑淡定...')
    print(f'   Open ID: {ZHENG_OPEN_ID}')
    
    result = send_message(token, ZHENG_OPEN_ID, '你好，我是小龙虾助手。这是一条测试消息。')
    print(f'\n3. 结果:')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result.get('code') == 0:
        print('\n✅ 消息发送成功！')
        print('\n现在：')
        print('1. 郑淡定会收到这条消息')
        print('2. 如果郑淡定回复，就建立了单聊会话')
        print('3. 之后可以获取这个单聊的聊天记录')
    else:
        print('\n发送失败:', result.get('msg'))
        print('\n可能原因：')
        print('- 郑淡定是外部联系人，机器人无法直接发消息')
        print('- 需要郑淡定先添加机器人为好友')

if __name__ == '__main__':
    main()
