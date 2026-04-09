#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书聊天记录每日总结 - 手动执行
"""

import json
import os
from datetime import datetime, timedelta

# 计算昨天的时间范围
yesterday = datetime.now() - timedelta(days=1)
start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

print("=" * 60)
print("飞书聊天记录每日总结")
print("=" * 60)
print(f"\n[日期] 查询时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')}")

# 检查飞书配置文件
config_paths = [
    os.path.expanduser("~/.lark-cli/config.json"),
    os.path.expanduser("~/.workbuddy/feishu_config.json"),
]

config_found = False
for config_path in config_paths:
    if os.path.exists(config_path):
        print(f"\n[配置] 找到飞书配置文件: {config_path}")
        config_found = True
        break

if not config_found:
    print("\n[警告] 未找到飞书配置文件")
    print("       请先配置飞书 CLI 或 WorkBuddy 飞书渠道")

# 生成报告
print("\n" + "=" * 60)
print("生成报告...")
print("=" * 60)

report = f"""# 飞书聊天记录每日总结

**统计日期**: {yesterday.strftime('%Y年%m月%d日')}  
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 消息统计

| 类别 | 数量 | 占比 |
|------|------|------|
| 单聊消息 | -- | --% |
| 群聊消息 | -- | --% |
| 图片消息 | -- | --% |
| 文件消息 | -- | --% |

## 单聊记录

_需要配置飞书 CLI 并登录后才能获取实际数据_

## 群聊记录

_需要配置飞书 CLI 并登录后才能获取实际数据_

---

## 配置说明

当前状态: {'已配置' if config_found else '未配置'}

如需获取真实数据，请：
1. 安装飞书 CLI: `npm install -g @larksuite/cli`
2. 登录飞书: `lark-cli login`
3. 或配置 WorkBuddy 飞书渠道

"""

print(report)

# 保存报告
report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_summary_{yesterday.strftime('%Y%m%d')}.md"
with open(report_file, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\n[完成] 报告已保存到: {report_file}")
print("=" * 60)
