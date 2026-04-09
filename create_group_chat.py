#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建群聊并邀请成员"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

APP_ID = 'cli_a93fb4f24f785bc3'
APP_SECRET = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'
# 郑淡定的 open_id
ZHENG_OPEN_ID = 'ou_12d9689fa81e05ed626f98734cebacc7'
# 机器人自己的 open_id
BOT_OPEN_ID = 'ou_84a12167590d600c343cce96c2bcf89e'

def get_tenant_token():
    """获取 tenant_access_token"""
    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    data = {'app_id': APP_ID, 'app_secret': APP_SECRET}
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        return result['tenant_access_token']

def create_chat(token, name, member_open_ids):
    """创建群聊"""
    url = 'https://open.feishu.cn/open-apis/im/v1/chats'
    data = {
        'name': name,
        'description': '工作沟通群',
        'chat_mode': 'group',
        'chat_type': 'public',  # 公开群
        'owner_id': BOT_OPEN_ID,
        'user_id_list': member_open_ids
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
    print('创建群聊')
    print('=' * 60)
    
    token = get_tenant_token()
    print('\n1. 获取 Tenant Token 成功')
    
    # 创建群聊，包含机器人和郑淡定
    print('\n2. 创建群聊...')
    print(f'   成员: 机器人 + 郑淡定 ({ZHENG_OPEN_ID})')
    
    result = create_chat(token, '滕成-郑淡定-工作群', [ZHENG_OPEN_ID])
    
    print(f'\n3. 结果:')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result.get('code') == 0:
        chat_id = result['data']['chat_id']
        print(f'\n✅ 群聊创建成功！')
        print(f'   Chat ID: {chat_id}')
        print(f'\n现在机器人可以获取这个群聊的消息了')
    else:
        print(f'\n❌ 创建失败: {result.get("msg")}')
        print('\n可能的原因：')
        print('1. 郑淡定是外部联系人，机器人无法直接邀请')
        print('2. 需要用户手动创建群聊')
        print('\n建议：请在飞书中手动创建群聊，然后添加机器人为成员')

if __name__ == '__main__':
    main()
