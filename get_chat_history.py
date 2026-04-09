#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import urllib.request
import json

app_id = 'cli_a93fb4f24f785bc3'
app_secret = '3bbpjT33nUbpR4dOpFuajgwfyI5qakwG'

# 获取 token
auth_url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
auth_data = json.dumps({'app_id': app_id, 'app_secret': app_secret}).encode()
req = urllib.request.Request(auth_url, data=auth_data, method='POST')
req.add_header('Content-Type', 'application/json')

with urllib.request.urlopen(req, timeout=10) as resp:
    auth_result = json.loads(resp.read())
    token = auth_result['tenant_access_token']

# 获取所有会话的消息
chats_url = 'https://open.feishu.cn/open-apis/im/v1/chats?page_size=50'
req2 = urllib.request.Request(chats_url, method='GET')
req2.add_header('Authorization', f'Bearer {token}')

with urllib.request.urlopen(req2, timeout=10) as resp:
    chats = json.loads(resp.read())
    items = chats.get('data', {}).get('items', [])
    
    all_messages = []
    
    for item in items:
        chat_id = item.get('chat_id')
        name = item.get('name') or '(no name)'
        
        # 获取该会话的消息
        msg_url = f'https://open.feishu.cn/open-apis/im/v1/messages?container_id={chat_id}&container_id_type=chat&page_size=20'
        req3 = urllib.request.Request(msg_url, method='GET')
        req3.add_header('Authorization', f'Bearer {token}')
        
        try:
            with urllib.request.urlopen(req3, timeout=10) as resp2:
                msgs = json.loads(resp2.read())
                if msgs.get('code') == 0:
                    msg_items = msgs.get('data', {}).get('items', [])
                    for m in msg_items:
                        sender = m.get('sender', {}).get('sender_id', {}).get('open_id', 'unknown')
                        msg_type = m.get('msg_type', 'unknown')
                        content_str = m.get('content', '{}')
                        create_time = m.get('create_time', '')
                        
                        # 解析内容
                        try:
                            content = json.loads(content_str)
                            if msg_type == 'text':
                                text = content.get('text', '')
                            else:
                                text = f'[{msg_type}] {content_str[:50]}'
                        except:
                            text = content_str[:50]
                        
                        all_messages.append({
                            'time': create_time,
                            'chat': name,
                            'sender': sender,
                            'text': text
                        })
        except Exception as e:
            pass
    
    # 按时间排序
    all_messages.sort(key=lambda x: x['time'])
    
    print(f'Total messages: {len(all_messages)}')
    for m in all_messages:
        time_str = m['time'][:19] if len(m['time']) > 19 else m['time']
        chat_str = m['chat'][:15]
        sender_str = m['sender'][:20]
        text_str = m['text'][:50]
        print(f"[{time_str}] {chat_str} | {sender_str} | {text_str}")
