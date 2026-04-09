import time
import pyautogui
import pyperclip
import sys
import ctypes
import ctypes.wintypes

CONTACT = sys.argv[1].strip('"').strip("'") if len(sys.argv) > 1 else "filehelper"
MESSAGE = sys.argv[2].strip('"').strip("'") if len(sys.argv) > 2 else ""
SCREENSHOT_PATH = r"c:\Users\Lenovo\WorkBuddy\Claw\wechat_screenshot.png"

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = False

def find_and_activate_wechat():
    hwnd = ctypes.windll.user32.FindWindowW(None, "\u5fae\u4fe1")
    if hwnd == 0:
        hwnd = ctypes.windll.user32.FindWindowW(None, "WeChat")
    if hwnd == 0:
        print("ERROR: WeChat window not found!")
        sys.exit(1)
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(1)
    print("OK WeChat activated hwnd=" + str(hwnd))
    return hwnd

hwnd = find_and_activate_wechat()

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
win_x = rect.left
win_y = rect.top
win_w = rect.right - rect.left
win_h = rect.bottom - rect.top

# 1. Ctrl+F 打开搜索
pyautogui.hotkey('ctrl', 'f')
time.sleep(0.8)

# 2. 粘贴联系人名称
pyperclip.copy(CONTACT)
pyautogui.hotkey('ctrl', 'v')
time.sleep(1.2)

# 3. 点击第一行搜索结果
# 微信搜索结果列表：第一行约 y=100
result_x = win_x + int(win_w * 0.18)
result_y = win_y + 100
print("Clicking 1st result at: %d, %d" % (result_x, result_y))
pyautogui.click(result_x, result_y)
time.sleep(1.5)

# 截图确认是否进入聊天窗口
screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
screenshot.save(SCREENSHOT_PATH)
print("SCREENSHOT_AFTER_CLICK:" + SCREENSHOT_PATH)

# 4. 点击消息输入框
input_x = win_x + win_w // 2
input_y = win_y + int(win_h * 0.88)
pyautogui.click(input_x, input_y)
time.sleep(0.5)

# 5. 粘贴并发送消息
pyperclip.copy(MESSAGE)
pyautogui.hotkey('ctrl', 'v')
time.sleep(0.3)
pyautogui.press('enter')
time.sleep(0.8)

# 截图确认发送
screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
screenshot.save(r"c:\Users\Lenovo\WorkBuddy\Claw\wechat_after_send.png")
print("SCREENSHOT_AFTER_SEND:c:\\Users\\Lenovo\\WorkBuddy\\Claw\\wechat_after_send.png")
print("DONE: " + MESSAGE + " -> " + CONTACT)

