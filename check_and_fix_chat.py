#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查并修复群聊"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

USER_TOKEN = 'u-dZkHKjpYt45X7NfsPOyovq0gmYRwh5ijo2Ga6M002e6.'
CHAT_ID = 'oc_3482d5558ae490e7b176959720488710'
ZHENG_OPEN_ID = 'ou_12d9689fa81e05ed626f98734cebacc7'

def api_call(url, method="GET", data=None, headers=None):
    """调用飞书 API"""
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data:
        req.data = json.dumps(data).encode()
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def main():
    print('=' * 60)
    print('检查群聊详情')
    print('=' * 60)
    
    headers = {'Authorization': f'Bearer {USER_TOKEN}'}
    
    # 1. 获取群聊详情
    print('\n1. 获取群聊详情...')
    chat_url = f'https://open.feishu.cn/open-apis/im/v1/chats/{CHAT_ID}'
    result = api_call(chat_url, headers=headers)
    
    if result.get('code') == 0:
        chat = result['data']
        print(f"   名称: {chat.get('name') or '(无主题)'}")
        print(f"   Chat ID: {chat.get('chat_id')}")
        print(f"   类型: {chat.get('chat_type')}")
        print(f"   成员数: {chat.get('member_count', 'Unknown')}")
    else:
        print(f"   获取失败: {result.get('msg')}")
    
    # 2. 获取群成员列表
    print('\n2. 获取群成员列表...')
    members_url = f'https://open.feishu.cn/open-apis/im/v1/chats/{CHAT_ID}/members?page_size=100'
    result = api_call(members_url, headers=headers)
    
    if result.get('code') == 0:
        members = result['data'].get('items', [])
        print(f"   成员数: {len(members)}")
        for m in members:
            print(f"   - {m.get('name', 'Unknown')} ({m.get('member_id', 'N/A')})")
    else:
        print(f"   获取失败: {result.get('msg')}")
    
    # 3. 尝试再次邀请郑淡定
    print('\n3. 尝试再次邀请郑淡定...')
    invite_url = f'https://open.feishu.cn/open-apis/im/v1/chats/{CHAT_ID}/members'
    invite_data = {
        'id_list': [ZHENG_OPEN_ID],
        'member_type': 'open_id'
    }
    
    result = api_call(invite_url, method='POST', data=invite_data, headers=headers)
    print(f"   结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    # 4. 更新群聊名称
    print('\n4. 更新群聊名称...')
    update_url = f'https://open.feishu.cn/open-apis/im/v1/chats/{CHAT_ID}'
    update_data = {
        'name': '滕成-郑淡定-工作群'
    }
    
    result = api_call(update_url, method='PUT', data=update_data, headers=headers)
    print(f"   结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if result.get('code') == 0:
        print('\n✅ 群聊名称已更新！')
    else:
        print(f'\n⚠️ 更新名称失败: {result.get("msg")}')

if __name__ == '__main__':
    main()
