"""
示例：生成项目安排图片并发送
"""
import sys
sys.path.insert(0, '..')

from image_generator import create_schedule_image
from wechat_sender import send_image

# 定义项目安排
days = [
    ("周一", [
        "数据库设计",
        "聊天记录学习模块开发",
        "初步测试与调试"
    ]),
    ("周二", [
        "自动回复逻辑开发",
        "资料发送功能集成",
        "飞书平台同步接口"
    ]),
    ("周三上午", [
        "整体联调测试",
        "11:00前 Bug修复与优化",
        "12:00前 项目交付与演示"
    ])
]

milestones = [
    "周一晚：完成核心功能开发",
    "周二晚：完成第三方集成", 
    "周三中午：最终交付演示"
]

# 生成图片
print("生成项目安排图片...")
image_path = create_schedule_image(
    title="项目时间安排",
    period="周一 → 周三中午",
    goal="微信助手开发与客户自动化成交系统",
    days=days,
    milestones=milestones,
    footer="有任何问题请随时沟通！"
)
print(f"图片已生成: {image_path}")

# 发送图片
print("\n发送图片给尹国锋...")
send_image("尹国锋", image_path, "请查看项目时间安排")

print("\n完成！")
