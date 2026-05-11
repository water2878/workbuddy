#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理群聊@消息并自动回复
用法: python reply_group_at.py "[GROUP@群名] [提问者]: 问题内容"
"""
import sys
sys.path.insert(0, 'sender')
sys.path.insert(0, 'core')

from group_reply_handler import handle_group_at

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python reply_group_at.py \"[GROUP@群名] [提问者]: 问题\"")
        print("示例: python reply_group_at.py \"[GROUP@升降桌群] [张三]: @李生 多少钱？\"")
        sys.exit(1)
    
    message = sys.argv[1]
    
    print(f"处理群聊@消息: {message[:50]}...")
    
    # 处理@消息
    result = handle_group_at(message)
    
    if result['handled']:
        print(f"✅ 已处理群聊@")
        print(f"   群组: {result['group']}")
        print(f"   提问者: {result['sender']}")
        print(f"   回复: {result['reply']}")
        if result['result'].get('success'):
            print(f"✅ 回复发送成功")
        else:
            print(f"❌ 回复发送失败: {result['result'].get('error')}")
    else:
        print(f"⏭️ 非@消息，跳过")
