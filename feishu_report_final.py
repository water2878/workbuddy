#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成并发送飞书聊天记录总结报告
"""

from datetime import datetime, timedelta

yesterday = datetime.now() - timedelta(days=1)

# 群聊数据（从API获取）
chats = [
    {"name": "龙虾繁殖基地", "chat_id": "oc_47ec374827424133a4f739ab7f576454", "external": True, "status": "normal"},
    {"name": "滕成's Feishu Assistant", "chat_id": "oc_37a7b3789a1e2e0a0dea2d38d1986d6a", "external": True, "status": "normal"},
    {"name": "哈哈哈哈哈哈哈", "chat_id": "oc_0170529c7f11a6faa43785a6910d4cf1", "external": False, "status": "normal"},
    {"name": "用户751423's FeiShu customer service", "chat_id": "oc_4235aae7490f1419aa7587e8d2532a64", "external": True, "status": "normal"},
    {"name": "滕成, 郑淡定", "chat_id": "oc_b983b2251ab84855ad60b8b6bc6ea221", "external": True, "status": "dissolved"},
    {"name": "(未命名群聊)", "chat_id": "oc_404fd89cfd630997988ec40b125bb39d", "external": False, "status": "normal"},
    {"name": "(未命名群聊)", "chat_id": "oc_a8401c47e18bc2ff060596924bef6c3f", "external": False, "status": "normal"},
    {"name": "滕成, 郑淡定", "chat_id": "oc_9525ce916a81daea68614da758015130", "external": True, "status": "dissolved"},
    {"name": "(未命名群聊)", "chat_id": "oc_3482d5558ae490e7b176959720488710", "external": False, "status": "normal"},
    {"name": "郑淡定, 用户751423", "chat_id": "oc_23e4b70736d57e7dab7adcc4427190a1", "external": True, "status": "normal"},
    {"name": "【用户751423 妙搭技术服务工单群】", "chat_id": "oc_c0ba3730537f4d1339515fdfaab95b6a", "external": True, "status": "normal"},
]

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
    f"| 类别 | 数量 |",
    f"|------|------|",
    f"| 群聊总数 | {len(chats)} |",
    f"| 外部群聊 | {sum(1 for c in chats if c['external'])} |",
    f"| 内部群聊 | {sum(1 for c in chats if not c['external'])} |",
    f"| 活跃群聊 | {sum(1 for c in chats if c['status'] == 'normal')} |",
    f"| 已解散 | {sum(1 for c in chats if c['status'] == 'dissolved')} |",
    "| 单聊消息 | 需要 im:message 权限 |",
    "| 图片消息 | 需要 im:resource 权限 |",
    "",
    "---",
    "",
    "## 群聊列表",
    "",
]

# 分类显示群聊
normal_chats = [c for c in chats if c['status'] == 'normal']
dissolved_chats = [c for c in chats if c['status'] == 'dissolved']

report_lines.append("### 活跃群聊")
report_lines.append("")
for chat in normal_chats:
    ext = "外部" if chat['external'] else "内部"
    report_lines.append(f"- **{chat['name']}** ({ext})")

if dissolved_chats:
    report_lines.append("")
    report_lines.append("### 已解散群聊")
    report_lines.append("")
    for chat in dissolved_chats:
        ext = "外部" if chat['external'] else "内部"
        report_lines.append(f"- ~~{chat['name']}~~ ({ext}, 已解散)")

report_lines.extend([
    "",
    "---",
    "",
    "## 使用用户权限获取的数据",
    "",
    "[OK] 已成功使用用户权限 (user) 获取群聊列表",
    "",
    "**注意**: 要获取完整聊天记录内容，需要应用具备以下权限：",
    "- `im:message:readonly` - 读取消息",
    "- `im:resource:readonly` - 读取图片/文件",
    "- `im:chat:readonly` - 读取群聊信息",
    "",
    "---",
    "",
    "**App ID**: cli_a93fb4f24f785bc3",
    "**用户**: 用户751423",
])

report = '\n'.join(report_lines)

# 保存报告
report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/feishu_summary_{yesterday.strftime('%Y%m%d')}_final.md"
with open(report_file, 'w', encoding='utf-8') as f:
    f.write(report)

print("=" * 60)
print("飞书聊天记录每日总结 - 用户权限")
print("=" * 60)
print(f"\n[日期] {yesterday.strftime('%Y年%m月%d日')}")
print(f"[群聊] 共 {len(chats)} 个群聊")
print(f"       - 外部群聊: {sum(1 for c in chats if c['external'])}")
print(f"       - 内部群聊: {sum(1 for c in chats if not c['external'])}")
print(f"       - 已解散: {sum(1 for c in chats if c['status'] == 'dissolved')}")
print("\n[报告已生成]")
print(f"文件: {report_file}")
print("=" * 60)

# 显示报告
print("\n报告内容预览:")
print("=" * 60)
print(report)
