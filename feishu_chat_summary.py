#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书聊天记录每日总结 - 使用飞书 API
"""

import requests
import json
import os
from datetime import datetime, timedelta

# 飞书配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"

BASE_URL = "https://open.feishu.cn/open-apis"

class FeishuClient:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_access_token = None
        
    def get_tenant_access_token(self):
        """获取 tenant_access_token"""
        url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json"}
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                self.tenant_access_token = result["tenant_access_token"]
                return True
            else:
                print(f"[错误] 获取 token 失败: {result}")
                return False
        except Exception as e:
            print(f"[错误] 请求失败: {e}")
            return False
    
    def get_chat_list(self):
        """获取聊天列表（需要 user_access_token，这里简化处理）"""
        # 获取用户所在的群聊列表
        url = f"{BASE_URL}/chat/v4/list"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            print(f"[错误] 获取聊天列表失败: {e}")
            return None

def main():
    print("=" * 60)
    print("飞书聊天记录每日总结")
    print("=" * 60)
    
    # 计算昨天的时间范围
    yesterday = datetime.now() - timedelta(days=1)
    start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    print(f"\n[日期] 查询时间: {yesterday.strftime('%Y年%m月%d日')}")
    print(f"[时间] {start_time.strftime('%H:%M')} ~ {end_time.strftime('%H:%M')}")
    
    # 初始化飞书客户端
    client = FeishuClient(APP_ID, APP_SECRET)
    
    print("\n[连接] 正在连接飞书 API...")
    if not client.get_tenant_access_token():
        print("[失败] 无法获取访问令牌")
        return
    
    print("[成功] 已获取访问令牌")
    
    # 尝试获取聊天列表
    print("\n[获取] 正在获取聊天列表...")
    chat_list = client.get_chat_list()
    
    if chat_list and chat_list.get("code") == 0:
        groups = chat_list.get("data", {}).get("groups", [])
        print(f"[成功] 找到 {len(groups)} 个群聊")
        
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
            "| 类别 | 数量 |",
            "|------|------|",
            f"| 群聊数量 | {len(groups)} |",
            "| 单聊消息 | 需要 user_access_token |",
            "| 图片消息 | 需要 user_access_token |",
            "| 文件消息 | 需要 user_access_token |",
            "",
            "---",
            "",
            "## 群聊列表",
            "",
        ]
        
        for group in groups[:10]:  # 只显示前10个
            name = group.get("name", "未命名群聊")
            chat_id = group.get("chat_id", "")
            report_lines.append(f"- **{name}** (ID: {chat_id})")
        
        if len(groups) > 10:
            report_lines.append(f"\n... 还有 {len(groups) - 10} 个群聊")
        
        report_lines.extend([
            "",
            "---",
            "",
            "## 说明",
            "",
            "**注意**: 要获取完整聊天记录，需要：",
            "1. 获取 user_access_token（需要用户授权）",
            "2. 使用 message API 拉取历史消息",
            "3. 或使用飞书事件订阅实时接收消息",
            "",
            f"**App ID**: {APP_ID}",
            f"**用户 Open ID**: {USER_OPEN_ID}",
        ])
        
    else:
        error_msg = chat_list.get("msg", "未知错误") if chat_list else "请求失败"
        print(f"[警告] 获取聊天列表失败: {error_msg}")
        
        report_lines = [
            "# 飞书聊天记录每日总结",
            "",
            f"**统计日期**: {yesterday.strftime('%Y年%m月%d日')}",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## 状态",
            "",
            f"**连接状态**: 部分成功",
            "",
            f"**错误信息**: {error_msg}",
            "",
            "---",
            "",
            "## 可能的原因",
            "",
            "1. 应用权限不足（需要开通 `chat:chat:readonly` 权限）",
            "2. 需要用户授权才能读取消息",
            "3. 机器人需要被添加到群聊中",
            "",
            "---",
            "",
            f"**App ID**: {APP_ID}",
        ]
    
    report = "\n".join(report_lines)
    print("\n" + "=" * 60)
    print("报告预览:")
    print("=" * 60)
    print(report)
    
    # 保存报告
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_summary_{yesterday.strftime('%Y%m%d')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print(f"[完成] 报告已保存: {report_file}")
    print("=" * 60)

if __name__ == "__main__":
    main()
