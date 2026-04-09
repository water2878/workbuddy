#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取飞书所有聊天记录 - 群聊 + 单聊（使用飞书套件）
"""

import subprocess
import json
import re
from datetime import datetime, timedelta

def run_lark_cli(args):
    """运行 lark-cli 命令"""
    cmd = ["npx", "-y", "@larksuite/cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=60)
    return result.stdout, result.stderr, result.returncode

def parse_json_output(output):
    """从输出中提取 JSON"""
    # 找到 { 开头的行
    for line in output.split('\n'):
        line = line.strip()
        if line and line.startswith('{'):
            try:
                return json.loads(line)
            except:
                pass
    return None

def main():
    print("=" * 70)
    print("飞书聊天记录每日总结 - 完整版")
    print("=" * 70)
    
    yesterday = datetime.now() - timedelta(days=1)
    start_time = "2026-04-07T00:00:00+08:00"
    end_time = "2026-04-07T23:59:59+08:00"
    
    print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
    
    all_messages = []
    
    # 1. 获取单聊消息 (p2p)
    print("\n" + "-" * 70)
    print("[1/2] 获取单聊消息 (p2p)")
    print("-" * 70)
    
    stdout, stderr, rc = run_lark_cli([
        "im", "+messages-search",
        "--start", start_time,
        "--end", end_time,
        "--chat-type", "p2p",
        "--as", "user",
        "--page-size", "50"
    ])
    
    result = parse_json_output(stdout)
    if result and result.get("ok"):
        p2p_messages = result.get("data", {}).get("messages", [])
        print(f"[成功] 获取到 {len(p2p_messages)} 条单聊消息")
        for msg in p2p_messages:
            msg['chat_category'] = '单聊'
        all_messages.extend(p2p_messages)
    else:
        print(f"[失败] 无法获取单聊消息")
        p2p_messages = []
    
    # 2. 获取群聊消息 (group)
    print("\n" + "-" * 70)
    print("[2/2] 获取群聊消息 (group)")
    print("-" * 70)
    
    stdout, stderr, rc = run_lark_cli([
        "im", "+messages-search",
        "--start", start_time,
        "--end", end_time,
        "--chat-type", "group",
        "--as", "user",
        "--page-size", "50"
    ])
    
    result = parse_json_output(stdout)
    if result and result.get("ok"):
        group_messages = result.get("data", {}).get("messages", [])
        print(f"[成功] 获取到 {len(group_messages)} 条群聊消息")
        for msg in group_messages:
            msg['chat_category'] = '群聊'
        all_messages.extend(group_messages)
    else:
        print(f"[失败] 无法获取群聊消息")
        group_messages = []
    
    # 生成报告
    print("\n" + "=" * 70)
    print("生成完整报告")
    print("=" * 70)
    
    print(f"\n[统计]")
    print(f"  单聊消息: {len(p2p_messages)} 条")
    print(f"  群聊消息: {len(group_messages)} 条")
    print(f"  总计: {len(all_messages)} 条")
    
    # 按时间排序
    all_messages.sort(key=lambda x: x.get('create_time', ''), reverse=True)
    
    # 构建报告
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
        f"| 群聊消息 | {len(group_messages)} |",
        f"| **总计** | **{len(all_messages)}** |",
        "",
        "---",
        "",
    ]
    
    # 单聊消息
    if p2p_messages:
        report_lines.extend([
            "## 单聊消息",
            "",
        ])
        for msg in p2p_messages[:20]:
            create_time = msg.get('create_time', '未知')
            content = msg.get('content', '')
            msg_type = msg.get('msg_type', 'unknown')
            sender = msg.get('sender', {})
            sender_type = sender.get('sender_type', 'unknown')
            
            # 清理内容
            content = re.sub(r'<[^>]+>', '', content)  # 移除 HTML 标签
            if len(content) > 200:
                content = content[:200] + "..."
            
            report_lines.append(f"**{create_time}** [{sender_type}]")
            report_lines.append(f"> {content}")
            report_lines.append("")
    
    # 群聊消息
    if group_messages:
        report_lines.extend([
            "## 群聊消息",
            "",
        ])
        for msg in group_messages[:20]:
            create_time = msg.get('create_time', '未知')
            content = msg.get('content', '')
            msg_type = msg.get('msg_type', 'unknown')
            sender = msg.get('sender', {})
            sender_type = sender.get('sender_type', 'unknown')
            chat_id = msg.get('chat_id', 'unknown')
            
            # 清理内容
            content = re.sub(r'<[^>]+>', '', content)
            if len(content) > 200:
                content = content[:200] + "..."
            
            report_lines.append(f"**{create_time}** [{sender_type}] {chat_id[:20]}...")
            report_lines.append(f"> {content}")
            report_lines.append("")
    
    report = '\n'.join(report_lines)
    
    # 保存报告
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_complete_summary_{yesterday.strftime('%Y%m%d')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n[完成] 报告已保存: {report_file}")
    
    # 显示预览
    print("\n报告预览:")
    print("-" * 70)
    print(report[:3000])
    print("...")
    print("=" * 70)

if __name__ == "__main__":
    main()
