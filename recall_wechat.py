import time
import pyautogui
import pyperclip
import sys
import ctypes
import ctypes.wintypes

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
    return hwnd

hwnd = find_and_activate_wechat()

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
win_x = rect.left
win_y = rect.top
win_w = rect.right - rect.left
win_h = rect.bottom - rect.top

# 右键点击最后一条消息（聊天区域右下方附近）
msg_x = win_x + int(win_w * 0.6)
msg_y = win_y + int(win_h * 0.78)
print("Right clicking last message at: %d, %d" % (msg_x, msg_y))
pyautogui.rightClick(msg_x, msg_y)
time.sleep(1)

# 截图看右键菜单
screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
screenshot.save(r"c:\Users\Lenovo\WorkBuddy\Claw\wechat_rightclick.png")
print("SCREENSHOT_SAVED")
