#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取与郑淡定的单聊聊天记录
"""
import urllib.request
import json

USER_TOKEN = "u-fJY3wXf1BarbFBKlEqE21v5k3W_B15gPPE2aUBM02e69"
ZHENG_OPEN_ID = "ou_12d9689fa81e05ed626f98734cebacc7"

def api_call(url, method="GET", data=None, headers=None):
    """调用飞书 API"""
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data:
        req.data = data.encode()
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except:
            return {'code': e.code, 'msg': str(e)}

def main():
    headers = {'Authorization': f'Bearer {USER_TOKEN}'}
    
    print("=" * 60)
    print("获取与郑淡定的聊天记录")
    print("=" * 60)
    
    # 1. 获取当前用户信息
    print("\n[1] 获取当前用户信息...")
    # 跳过获取用户信息，直接使用已知值
    my_open_id = None
    print("  跳过（使用消息中的发送者信息）")
    
    # 2. 获取单聊会话列表
    print("\n[2] 获取单聊会话列表...")
    chats_url = "https://open.feishu.cn/open-apis/im/v1/chats?chat_type=p2p&page_size=50"
    result = api_call(chats_url, headers=headers)
    
    target_chat_id = None
    if result.get('code') == 0:
        items = result.get('data', {}).get('items', [])
        print(f"  找到 {len(items)} 个单聊会话")
        for item in items:
            chat_id = item.get('chat_id')
            name = item.get('name', '无名称')
            print(f"    - {chat_id}: {name}")
            # 检查是否包含郑淡定
            if ZHENG_OPEN_ID in str(item) or '郑淡定' in name:
                target_chat_id = chat_id
                print(f"      >> 找到与郑淡定的会话!")
    else:
        print(f"  失败: {result.get('msg', result)}")
    
    # 3. 如果没有找到，尝试用郑淡定的 open_id 直接获取消息
    if not target_chat_id:
        print("\n[3] 尝试直接获取与郑淡定的消息...")
        # 使用郑淡定的 open_id 作为 container_id
        msg_url = f"https://open.feishu.cn/open-apis/im/v1/messages?container_id={ZHENG_OPEN_ID}&container_id_type=open_id&page_size=50"
        result = api_call(msg_url, headers=headers)
        
        if result.get('code') == 0:
            items = result.get('data', {}).get('items', [])
            print(f"  找到 {len(items)} 条消息")
            target_chat_id = ZHENG_OPEN_ID
        else:
            print(f"  失败: {result.get('msg', result)}")
            # 尝试其他方式
            print("\n[4] 尝试获取所有消息...")
            msg_url2 = "https://open.feishu.cn/open-apis/im/v1/messages?page_size=50"
            result = api_call(msg_url2, headers=headers)
            if result.get('code') == 0:
                items = result.get('data', {}).get('items', [])
                print(f"  找到 {len(items)} 条消息")
            else:
                print(f"  失败: {result.get('msg', result)}")
                return
    else:
        # 4. 获取会话消息
        print(f"\n[3] 获取会话 {target_chat_id} 的消息...")
        msg_url = f"https://open.feishu.cn/open-apis/im/v1/messages?container_id={target_chat_id}&container_id_type=chat&page_size=50"
        result = api_call(msg_url, headers=headers)
        
        if result.get('code') == 0:
            items = result.get('data', {}).get('items', [])
            print(f"  找到 {len(items)} 条消息")
        else:
            print(f"  失败: {result.get('msg', result)}")
            return
    
    # 5. 显示消息
    print("\n" + "=" * 60)
    print("聊天记录")
    print("=" * 60)
    
    if not items:
        print("没有找到消息")
        return
    
    # 按时间排序
    items.sort(key=lambda x: x.get('create_time', ''))
    
    for msg in items:
        create_time = msg.get('create_time', '')
        sender = msg.get('sender', {}).get('sender_id', {}).get('open_id', 'unknown')
        msg_type = msg.get('msg_type', 'unknown')
        content_str = msg.get('content', '{}')
        
        # 解析时间
        if len(create_time) > 10:
            time_str = create_time[:19]
        else:
            time_str = create_time
        
        # 解析内容
        try:
            content = json.loads(content_str)
            if msg_type == 'text':
                text = content.get('text', '')
            elif msg_type == 'image':
                text = '[图片]'
            elif msg_type == 'file':
                text = '[文件]'
            else:
                text = f'[{msg_type}]'
        except:
            text = content_str[:50]
        
        # 判断发送者
        if sender == my_open_id:
            sender_name = "我"
        elif sender == ZHENG_OPEN_ID:
            sender_name = "郑淡定"
        else:
            sender_name = sender[:10]
        
        print(f"[{time_str}] {sender_name}: {text}")

if __name__ == "__main__":
    main()
