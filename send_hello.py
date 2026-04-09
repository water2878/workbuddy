#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给用户发送消息"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = 'cli_a93fb4f24f785bc3'
APP_SECRET = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'
USER_OPEN_ID = 'ou_4a86846caf437e8fda2fc9f2794c5424'

def get_tenant_token():
    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    data = {'app_id': APP_ID, 'app_secret': APP_SECRET}
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        return result['tenant_access_token']

def send_message(token, user_id, content):
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
    print('发送消息中...')
    token = get_tenant_token()
    result = send_message(token, USER_OPEN_ID, '你好')
    
    if result.get('code') == 0:
        print('消息发送成功！')
        print('请检查飞书，你应该收到了来自「小龙虾助手」的消息。')
    else:
        print('发送失败:', result.get('msg'))

if __name__ == '__main__':
    main()
