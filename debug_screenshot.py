# -*- coding: utf-8 -*-
import ctypes, ctypes.wintypes, time
import pyautogui

hwnd = 0
for title in ["微信", "WeChat"]:
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd:
        break

ctypes.windll.user32.ShowWindow(hwnd, 9)
time.sleep(0.3)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
x, y = rect.left, rect.top
w = rect.right - rect.left
h = rect.bottom - rect.top

# 截完整微信窗口
img = pyautogui.screenshot(region=(x, y, w, h))
img.save("debug_wechat_full.png")

# 截会话列表区域（监控用的区域）
lx = x + int(w * 0.0)
ly = y + int(h * 0.08)
lw = int(w * 0.32)
lh = int(h * 0.85)
img2 = pyautogui.screenshot(region=(lx, ly, lw, lh))
img2.save("debug_session_list.png")

print(f"窗口: {w}x{h} @ ({x},{y})")
print("截图已保存: debug_wechat_full.png / debug_session_list.png")
