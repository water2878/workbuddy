"""
示例：发送文字消息
"""
import sys
sys.path.insert(0, '..')

from wechat_sender import send_text, send_text_segments

# 示例1：发送单条消息
print("示例1：发送单条消息")
send_text("李昊", "你好，这是测试消息")

# 示例2：分段发送长消息
print("\n示例2：分段发送长消息")
messages = [
    "【项目汇报】",
    "",
    "一、今日完成",
    "• 功能A开发完成",
    "• 功能B测试通过",
    "",
    "二、明日计划",
    "• 继续优化性能",
    "• 完善文档"
]
send_text_segments("尹国锋", messages)

print("\n发送完成！")
