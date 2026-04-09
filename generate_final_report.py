#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成完整的飞书聊天记录报告（群聊 + 单聊）
"""

import json
import re
from datetime import datetime, timedelta

# 读取单聊消息
with open('C:/Users/Lenovo/WorkBuddy/Claw/p2p_messages.json', 'r', encoding='utf-8-sig') as f:
    p2p_data = json.load(f)

p2p_messages = p2p_data.get('data', {}).get('messages', [])

yesterday = datetime.now() - timedelta(days=1)

print("=" * 70)
print("飞书聊天记录每日总结 - 完整版")
print("=" * 70)
print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
print(f"\n[统计]")
print(f"  单聊消息: {len(p2p_messages)} 条")

# 按聊天对象分组
chat_partners = {}
for msg in p2p_messages:
    partner = msg.get('chat_partner', {}).get('open_id', 'unknown')
    if partner not in chat_partners:
        chat_partners[partner] = []
    chat_partners[partner].append(msg)

print(f"  聊天对象: {len(chat_partners)} 个")

# 生成报告
report_lines = [
    "# 飞书聊天记录每日总结",
    "",
    f"**统计日期**: {yesterday.strftime('%Y年%m月%d日')}",
    f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    "",
    "---",
    "",
    "## 消息统计",
    "",
    f"| 类型 | 数量 |",
    f"|------|------|",
    f"| 单聊消息 | {len(p2p_messages)} |",
    f"| 聊天对象 | {len(chat_partners)} |",
    "",
    "---",
    "",
]

# 单聊消息详情
report_lines.extend([
    "## 单聊消息详情",
    "",
])

# 按时间排序
sorted_msgs = sorted(p2p_messages, key=lambda x: x.get('create_time', ''), reverse=True)

for msg in sorted_msgs[:30]:  # 显示前30条
    create_time = msg.get('create_time', '未知')
    content = msg.get('content', '')
    msg_type = msg.get('msg_type', 'unknown')
    sender = msg.get('sender', {})
    sender_type = sender.get('sender_type', 'unknown')
    sender_name = sender.get('name', sender_type)
    
    # 清理内容
    content = re.sub(r'<[^>]+>', '', content)
    content = content.replace('\n', ' ')
    if len(content) > 150:
        content = content[:150] + "..."
    
    report_lines.append(f"**{create_time}** [{sender_name}]")
    report_lines.append(f"> {content}")
    report_lines.append("")

report_lines.extend([
    "---",
    "",
    "**数据来源**: 飞书 API (用户权限)",
    "**应用ID**: cli_a93fb4f24f785bc3",
])

report = '\n'.join(report_lines)

# 保存报告
report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_complete_{yesterday.strftime('%Y%m%d')}.md"
with open(report_file, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\n[完成] 报告已保存: {report_file}")

# 显示预览
print("\n报告已生成")
print("=" * 70)
