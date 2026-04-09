#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书聊天记录每日总结 - 使用用户权限获取完整数据
"""

import subprocess
import json
import os
from datetime import datetime, timedelta

# 飞书配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"

def run_lark_cli_command(args):
    """运行飞书 CLI 命令"""
    cmd = ["npx", "-y", "@larksuite/cli"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd="C:/Users/Lenovo/WorkBuddy/Claw",
            timeout=60,
            shell=True
        )
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1

def main():
    print("=" * 60)
    print("飞书聊天记录每日总结 (用户权限)")
    print("=" * 60)
    
    yesterday = datetime.now() - timedelta(days=1)
    
    print(f"\n[日期] 查询时间: {yesterday.strftime('%Y年%m月%d日')}")
    
    # 1. 获取群聊列表（用户权限）
    print("\n[步骤1] 获取群聊列表...")
    stdout, stderr, rc = run_lark_cli_command([
        "api", "GET", "/open-apis/im/v1/chats",
        "--params", '{"page_size":100}',
        "--as", "user"
    ])
    
    if rc != 0:
        print(f"[错误] 获取群聊失败: {stderr}")
        chats = []
    else:
        try:
            # 清理输出中的 XML 标记
            lines = stdout.split('\n')
            json_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('<') and not line.startswith('#'):
                    json_lines.append(line)
            
            if json_lines:
                result = json.loads('\n'.join(json_lines))
                if result.get('ok'):
                    chats = result.get('data', {}).get('items', [])
                    print(f"[成功] 获取到 {len(chats)} 个群聊")
                else:
                    print(f"[失败] API 返回错误: {result.get('error', {})}")
                    chats = []
            else:
                print("[错误] 无法解析响应")
                chats = []
        except Exception as e:
            print(f"[错误] 解析失败: {e}")
            print(f"[调试] 输出内容: {stdout[:500]}")
            chats = []
    
    # 2. 获取用户参与的群聊
    print("\n[步骤2] 获取用户会话列表...")
    # 使用 contact/v3 相关接口获取用户会话
    stdout, stderr, rc = run_lark_cli_command([
        "api", "GET", "/open-apis/contact/v3/users/me",
        "--as", "user"
    ])
    
    user_info = None
    if rc == 0:
        try:
            lines = [l for l in stdout.split('\n') if l.strip() and not l.startswith('<') and not l.startswith('#')]
            if lines:
                result = json.loads('\n'.join(lines))
                if result.get('ok'):
                    user_info = result.get('data', {})
                    print(f"[成功] 当前用户: {user_info.get('name', 'Unknown')}")
        except:
            pass
    
    if not user_info:
        print("[警告] 无法获取用户信息，可能需要重新登录")
    
    # 生成完整报告
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
        f"| 类别 | 数量 |",
        f"|------|------|",
        f"| 群聊数量 | {len(chats)} |",
        "| 单聊消息 | 需开通 im:message:readonly 权限 |",
        "| 图片消息 | 需开通 im:resource:readonly 权限 |",
        "| 文件消息 | 需开通 drive:drive:readonly 权限 |",
        "",
        "---",
        "",
        "## 群聊列表",
        "",
    ]
    
    if chats:
        for chat in chats[:20]:  # 显示前20个
            name = chat.get('name', '未命名群聊')
            chat_id = chat.get('chat_id', '')
            chat_type = chat.get('chat_type', 'group')
            member_count = chat.get('member_count', 0)
            
            report_lines.append(f"- **{name}** ({chat_type}, {member_count}人)")
    else:
        report_lines.append("_暂无群聊数据_")
    
    # 用户信息
    if user_info:
        report_lines.extend([
            "",
            "---",
            "",
            "## 当前用户信息",
            "",
            f"- **姓名**: {user_info.get('name', 'Unknown')}",
            f"- **Open ID**: {user_info.get('open_id', 'Unknown')}",
            f"- **User ID**: {user_info.get('user_id', 'Unknown')}",
        ])
    
    report_lines.extend([
        "",
        "---",
        "",
        "## 权限说明",
        "",
        "当前使用 **用户权限** 访问飞书 API，但要获取完整聊天记录需要以下权限：",
        "",
        "| 权限 | 用途 |",
        "|------|------|",
        "| `im:message:readonly` | 读取用户消息 |",
        "| `im:resource:readonly` | 读取图片/视频等资源 |",
        "| `drive:drive:readonly` | 读取云文档/文件 |",
        "| `contact:user.readonly` | 读取用户通讯录 |",
        "",
        "---",
        "",
        f"**App ID**: {APP_ID}",
        f"**用户**: {user_info.get('name', '用户751423') if user_info else '用户751423'}",
    ])
    
    report = '\n'.join(report_lines)
    
    # 保存报告
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_summary_{yesterday.strftime('%Y%m%d')}_full.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print("报告预览:")
    print("=" * 60)
    print(report[:2000] + "\n... [报告已截断]")
    
    print(f"\n[完成] 报告已保存: {report_file}")
    print("=" * 60)

if __name__ == "__main__":
    main()
