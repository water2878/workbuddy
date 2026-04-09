# -*- coding: utf-8 -*-
"""
截一张全屏，帮助确认左侧会话列表的坐标范围
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pyautogui
import time
import win32gui, win32con
import ctypes

def activate_wechat():
    hwnd = win32gui.FindWindow(None, "微信")
    if hwnd:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except:
            pass
        time.sleep(0.8)

activate_wechat()
time.sleep(0.5)

# 截全屏
img = pyautogui.screenshot()
img.save(r"C:\Users\Lenovo\WorkBuddy\Claw\wechat_full.png")
print(f"屏幕尺寸: {img.width} x {img.height}")
print("截图已保存到 wechat_full.png")
