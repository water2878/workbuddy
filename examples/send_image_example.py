"""
示例：发送图片
"""
import sys
sys.path.insert(0, '..')

from wechat_sender import send_image

# 示例1：发送图片（带文字说明）
print("示例1：发送图片（带文字说明）")
send_image("李昊", "../test_speed.png", "这是截图说明文字")

# 示例2：仅发送图片
print("\n示例2：仅发送图片")
send_image("李昊", "../test_speed.png")

print("\n发送完成！")
