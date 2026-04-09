import pyautogui
import ctypes
import ctypes.wintypes
import time
import os

# 先把微信移到屏幕内
hwnd = 0
for t in ['微信', 'WeChat']:
    hwnd = ctypes.windll.user32.FindWindowW(None, t)
    if hwnd: break

if hwnd:
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.3)
    ctypes.windll.user32.MoveWindow(hwnd, 100, 100, 1108, 706, True)
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    print('微信已移到屏幕内')

# 截取整个屏幕，让用户看清楚任务栏
screen_w = ctypes.windll.user32.GetSystemMetrics(0)
screen_h = ctypes.windll.user32.GetSystemMetrics(1)
print(f'屏幕分辨率: {screen_w}x{screen_h}')

# 截任务栏（底部）
shot = pyautogui.screenshot(region=(0, screen_h-120, screen_w, 120))
shot.save(r'C:\Users\Lenovo\WorkBuddy\Claw\taskbar_full.png')
print('任务栏截图已保存')

# 截取微信图标区域（任务栏右侧系统托盘附近，约右边 400px）
shot2 = pyautogui.screenshot(region=(screen_w-400, screen_h-80, 400, 80))
shot2.save(r'C:\Users\Lenovo\WorkBuddy\Claw\taskbar_right.png')
print('任务栏右侧截图已保存')
