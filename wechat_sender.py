"""
微信消息发送模块
支持：文字消息（分段）、图片发送
"""
import subprocess
import time
import random
import io
import pyautogui
import pyperclip
from pywinauto import keyboard
from pywinauto import Desktop
from PIL import Image

# 导入配置
try:
    from config import INPUT_BOX, WECHAT_ICON, SEARCH_RESULT
except ImportError:
    # 默认配置
    INPUT_BOX = (1437, 963)
    WECHAT_ICON = (1850, 1050)
    SEARCH_RESULT = (1100, 200)


def activate_wechat():
    """激活微信窗口 - 点击任务栏微信图标（最可靠）"""
    print("  激活微信窗口...")
    pyautogui.click(WECHAT_ICON[0], WECHAT_ICON[1])
    time.sleep(0.5)
    return True


def search_contact(search_name):
    """搜索并进入联系人聊天窗口"""
    keyboard.send_keys('^f')
    time.sleep(0.3)
    pyperclip.copy(search_name)
    keyboard.send_keys('^v')
    time.sleep(0.3)
    time.sleep(random.uniform(0.01, 0.05))
    keyboard.send_keys('{ENTER}')
    time.sleep(random.uniform(0.8, 1.2))


def send_single_message(message):
    """发送单条消息"""
    clean_msg = message.replace('\n', ' ').replace('\r', ' ')
    pyperclip.copy(clean_msg)
    time.sleep(0.1)  # 减少延迟
    keyboard.send_keys('^v')
    time.sleep(0.2)  # 减少延迟
    keyboard.send_keys('{ENTER}')
    time.sleep(0.3)  # 减少延迟


def send_text(search_name, message):
    """
    发送文字消息给指定联系人
    自动处理换行符，将换行替换为空格
    """
    print(f"发送消息给 {search_name}...")
    
    activate_wechat()
    search_contact(search_name)
    
    pyautogui.click(*INPUT_BOX)
    time.sleep(0.2)
    
    send_single_message(message)
    
    print(f"[OK] 已发送给 {search_name}")


def send_text_segments(search_name, messages):
    """
    分段发送多条消息给指定联系人
    messages: 消息列表，每条消息单独发送
    适合发送结构化的长消息，提高可读性
    """
    print(f"发送 {len(messages)} 条消息给 {search_name}...")
    
    activate_wechat()
    search_contact(search_name)
    
    pyautogui.click(*INPUT_BOX)
    time.sleep(0.2)
    
    for i, msg in enumerate(messages, 1):
        if msg.strip():  # 跳过空行
            print(f"  发送第 {i}/{len(messages)} 条...")
            send_single_message(msg)
        else:
            # 空行也发送（用于分隔）
            keyboard.send_keys('{ENTER}')
            time.sleep(0.3)
    
    print(f"[OK] 已发送给 {search_name}")


def send_image(search_name, image_path, message=""):
    """
    发送图片给指定联系人
    search_name: 联系人名称
    image_path: 图片路径
    message: 可选的文字说明
    """
    print(f"发送图片给 {search_name}...")
    
    activate_wechat()
    search_contact(search_name)
    
    # 复制图片到剪贴板
    image = Image.open(image_path)
    output = io.BytesIO()
    image.convert('RGB').save(output, 'BMP')
    data = output.getvalue()[14:]  # 去掉BMP文件头
    output.close()
    
    import win32clipboard
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()
    
    # 粘贴图片
    pyautogui.click(*INPUT_BOX)
    time.sleep(0.3)
    keyboard.send_keys('^v')
    time.sleep(0.5)
    
    # 添加文字说明
    if message:
        time.sleep(0.3)
        pyperclip.copy(message)
        keyboard.send_keys('^v')
        time.sleep(0.3)
    
    # 发送
    time.sleep(0.5)
    keyboard.send_keys('{ENTER}')
    
    print(f"[OK] 图片已发送给 {search_name}")


# 兼容旧版本API
send = send_text


if __name__ == "__main__":
    # 测试代码
    print("微信发送模块")
    print("使用示例:")
    print("  from wechat_sender import send_text, send_text_segments, send_image")
    print("  send_text('李昊', '你好')")
    print("  send_text_segments('尹国锋', ['消息1', '消息2'])")
    print("  send_image('李昊', 'screenshot.png', '说明文字')")
