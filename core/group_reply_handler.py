# -*- coding: utf-8 -*-
"""
群聊@消息回复处理器
处理群聊中被@的消息，生成回复并发送
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sender'))

from wechat_sender import send_text_safe
from customer_profile import load_profile, add_interaction

# 机器人昵称（用于被@识别）
BOT_NAMES = ['CLAW', '李生', '畅腾', '智能升降桌', '升降桌李生']


def is_at_message(text: str) -> bool:
    """检测消息是否@了机器人"""
    text_upper = text.upper()
    at_patterns = ['@CLAW', '@李生', '@畅腾', '@升降桌', '@智能升降桌']
    for pattern in at_patterns:
        if pattern.upper() in text_upper:
            return True
    return False


def parse_at_message(text: str) -> dict:
    """
    解析@消息，提取群名、提问者、问题内容
    格式: [GROUP@群名] [提问者]: 问题内容
    """
    import re
    
    result = {
        'is_at': False,
        'group_name': '',
        'sender': '',
        'question': '',
        'original': text
    }
    
    # Match [GROUP@群名] [提问者]: 问题
    pattern = r'\[GROUP@([^\]]+)\]\s*\[([^\]]+)\]:\s*(.+)'
    match = re.match(pattern, text, re.DOTALL)
    
    if match:
        result['is_at'] = True
        result['group_name'] = match.group(1).strip()
        result['sender'] = match.group(2).strip()
        result['question'] = match.group(3).strip()
    
    return result


def generate_reply(question: str, sender: str, group_name: str) -> str:
    """
    生成回复内容
    这里可以接入AI模型或根据关键词匹配回复
    """
    # TODO: 接入AI模型生成回复
    # 临时简单回复
    replies = {
        '价格': f'@{sender} 你好！需要什么型号？多少数量？我报个实价。',
        '多少钱': f'@{sender} 你好！什么型号？多少套？',
        '报价': f'@{sender} 型号+数量，我报给你。',
        '在吗': f'@{sender} 在的，有什么可以帮你？',
        '你好': f'@{sender} 你好！需要什么升降桌？',
    }
    
    # 关键词匹配
    for keyword, reply in replies.items():
        if keyword in question:
            return reply
    
    # 默认回复
    return f'@{sender} 收到，请稍等。'


def send_group_reply(group_name: str, sender: str, reply_text: str) -> dict:
    """
    发送群聊回复
    
    Args:
        group_name: 群聊名称
        sender: 提问者昵称（用于@）
        reply_text: 回复内容
    
    Returns:
        {"success": True/False, "error": None/str}
    """
    # 在群聊中发送消息
    result = send_text_safe(group_name, reply_text)
    
    # 更新客户画像
    if result.get('success'):
        try:
            add_interaction(
                nickname=sender,
                interaction_type="群聊@回复",
                content=f"群{group_name}: {reply_text[:50]}...",
                intention="已回复群聊@",
                next_action="等待客户后续"
            )
        except Exception as e:
            print(f"[WARN] 画像更新失败: {e}")
    
    return result


def handle_group_at(text: str) -> dict:
    """
    处理群聊@消息的完整流程
    
    Args:
        text: WorkBuddy收到的消息文本
    
    Returns:
        {"handled": True/False, "result": {...}}
    """
    # 解析消息
    parsed = parse_at_message(text)
    
    if not parsed['is_at']:
        return {'handled': False, 'reason': 'Not an @ message'}
    
    # 生成回复
    reply = generate_reply(
        question=parsed['question'],
        sender=parsed['sender'],
        group_name=parsed['group_name']
    )
    
    # 发送回复
    result = send_group_reply(
        group_name=parsed['group_name'],
        sender=parsed['sender'],
        reply_text=reply
    )
    
    return {
        'handled': True,
        'result': result,
        'group': parsed['group_name'],
        'sender': parsed['sender'],
        'reply': reply
    }


if __name__ == "__main__":
    # 测试
    test_msg = "[GROUP@升降桌交流群] [张三]: @李生 这个价格能便宜吗？"
    result = handle_group_at(test_msg)
    print(f"处理结果: {result}")
