import time
import ctypes
import ctypes.wintypes
import pyautogui
from PIL import Image
import os

# 查找并激活微信窗口
def find_and_activate_wechat():
    print("正在查找微信窗口...")
    hwnd = ctypes.windll.user32.FindWindowW(None, "微信")
    if hwnd == 0:
        hwnd = ctypes.windll.user32.FindWindowW(None, "WeChat")
    if hwnd == 0:
        print("❌ 未找到微信窗口，请先打开微信")
        return None, None
    
    print("✅ 找到微信窗口，正在激活...")
    ctypes.windll.user32.ShowWindow(hwnd, 9)  # 显示窗口
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)  # 置于前台
    time.sleep(0.8)

    # 获取窗口信息
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win = {
        'x': rect.left,
        'y': rect.top,
        'w': rect.right - rect.left,
        'h': rect.bottom - rect.top
    }
    print(f"✅ 微信窗口信息: x={win['x']}, y={win['y']}, w={win['w']}, h={win['h']}")
    return hwnd, win

# 获取聊天内容区域
def get_chat_area(win):
    """返回聊天内容区域"""
    x = win['x'] + int(win['w'] * 0.26)
    y = win['y'] + int(win['h'] * 0.05)
    w = int(win['w'] * 0.74)
    h = int(win['h'] * 0.80)
    return x, y, w, h

# 测试截图功能
def test_screenshot():
    print("=" * 60)
    print("测试微信聊天窗口截图功能")
    print("=" * 60)
    
    # 1. 激活微信
    hwnd, win = find_and_activate_wechat()
    if not win:
        return
    
    # 2. 点击聊天标签（确保在消息列表页）
    chat_tab_x = win['x'] + int(win['w'] * 0.04)
    chat_tab_y = win['y'] + int(win['h'] * 0.08)
    print(f"点击聊天标签: x={chat_tab_x}, y={chat_tab_y}")
    pyautogui.click(chat_tab_x, chat_tab_y)
    time.sleep(0.8)
    
    # 3. 点击第一个联系人
    list_x = win['x'] + int(win['w'] * 0.05)
    list_width = int(win['w'] * 0.20)
    y_start = win['y'] + int(win['h'] * 0.12)
    row_height = 64
    
    click_x = list_x + list_width // 2
    click_y = y_start + row_height // 2
    print(f"点击第一个联系人: x={click_x}, y={click_y}")
    pyautogui.click(click_x, click_y)
    time.sleep(1)
    
    # 4. 获取聊天区域
    cx, cy, cw, ch = get_chat_area(win)
    print(f"聊天区域: x={cx}, y={cy}, w={cw}, h={ch}")
    
    # 5. 点击聊天区域确保焦点
    chat_center_x = cx + cw // 2
    chat_center_y = cy + ch // 2
    print(f"点击聊天区域确保焦点: x={chat_center_x}, y={chat_center_y}")
    pyautogui.click(chat_center_x, chat_center_y)
    time.sleep(0.5)
    
    # 6. 滚动到最底部
    print("滚动到最底部（最新消息）")
    pyautogui.hotkey('ctrl', 'end')
    time.sleep(0.5)
    
    # 7. 测试截图
    print("开始截图...")
    try:
        # 先截取整个微信窗口
        full_screenshot = pyautogui.screenshot(region=(win['x'], win['y'], win['w'], win['h']))
        full_save_path = os.path.join(os.getcwd(), "wechat_full_test.png")
        full_screenshot.save(full_save_path)
        print(f"✅ 完整窗口截图已保存: {full_save_path}")
        
        # 再截取聊天区域
        chat_screenshot = pyautogui.screenshot(region=(cx, cy, cw, ch))
        chat_save_path = os.path.join(os.getcwd(), "wechat_chat_test.png")
        chat_screenshot.save(chat_save_path)
        print(f"✅ 聊天区域截图已保存: {chat_save_path}")
        
        print("\n🎉 截图测试成功！")
        print(f"请查看以下文件:")
        print(f"- 完整窗口截图: {full_save_path}")
        print(f"- 聊天区域截图: {chat_save_path}")
        
    except Exception as e:
        print(f"❌ 截图失败: {e}")

if __name__ == "__main__":
    test_screenshot()
