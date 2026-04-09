#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用 user_access_token 创建群聊"""
import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

USER_TOKEN = 'u-dZkHKjpYt45X7NfsPOyovq0gmYRwh5ijo2Ga6M002e6.'
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
    print('使用 User Token 创建群聊')
    print('=' * 60)
    
    headers = {'Authorization': f'Bearer {USER_TOKEN}'}
    
    # 1. 验证 token
    print('\n1. 验证 user_access_token...')
    user_info_url = 'https://open.feishu.cn/open-apis/authen/v1/user_info'
    result = api_call(user_info_url, headers=headers)
    
    if result.get('code') == 0:
        user = result['data']
        print(f"   用户: {user.get('name', 'Unknown')}")
        print(f"   Open ID: {user.get('open_id', 'N/A')}")
    else:
        print(f"   验证失败: {result.get('msg', result)}")
        return
    
    # 2. 创建群聊
    print('\n2. 创建群聊...')
    print(f"   邀请成员: 郑淡定 ({ZHENG_OPEN_ID})")
    
    create_url = 'https://open.feishu.cn/open-apis/im/v1/chats'
    data = {
        'name': '滕成-郑淡定-工作群',
        'description': '工作沟通群',
        'chat_mode': 'group',
        'chat_type': 'public',
        'user_id_list': [ZHENG_OPEN_ID]
    }
    
    result = api_call(create_url, method='POST', data=data, headers=headers)
    print(f"   结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if result.get('code') == 0:
        chat_id = result['data']['chat_id']
        print(f'\n✅ 群聊创建成功！')
        print(f'   Chat ID: {chat_id}')
        
        # 3. 邀请机器人加入群聊
        print('\n3. 邀请机器人加入群聊...')
        bot_open_id = 'ou_84a12167590d600c343cce96c2bcf89e'
        invite_url = f'https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}/members'
        invite_data = {
            'id_list': [bot_open_id],
            'member_type': 'open_id'
        }
        
        invite_result = api_call(invite_url, method='POST', data=invite_data, headers=headers)
        print(f"   结果: {json.dumps(invite_result, indent=2, ensure_ascii=False)}")
        
        if invite_result.get('code') == 0:
            print('\n✅ 机器人已加入群聊！')
            print(f'\n现在你可以：')
            print(f'1. 在飞书中打开群聊「滕成-郑淡定-工作群」')
            print(f'2. 机器人可以获取这个群聊的消息了')
        else:
            print(f'\n⚠️ 邀请机器人失败: {invite_result.get("msg")}')
            print('请手动在群聊中添加机器人「小龙虾助手」')
    else:
        print(f'\n❌ 创建群聊失败: {result.get("msg")}')

if __name__ == '__main__':
    main()
