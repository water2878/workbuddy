# -*- coding: utf-8 -*-
"""
截取微信左侧导航栏并打印每个图标的大致 Y 坐标比例
"""
import ctypes, ctypes.wintypes, pyautogui, time
from PIL import Image

for title in ["微信", "WeChat"]:
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd: break

ctypes.windll.user32.ShowWindow(hwnd, 9)
time.sleep(0.5)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
x = rect.left
y = rect.top
w = rect.right  - rect.left
h = rect.bottom - rect.top
print(f"窗口: x={x} y={y} w={w} h={h}")

# 截整个左侧导航栏（宽约6%）放大保存
nav_w = int(w * 0.06)
shot = pyautogui.screenshot(region=(x, y, nav_w, h))

# 放大 3 倍方便看清
big = shot.resize((nav_w * 3, h * 3), Image.NEAREST)
out = "C:/Users/Lenovo/WorkBuddy/Claw/nav_bar_big.png"
big.save(out)
print(f"已保存放大图: {out}")
print(f"导航栏像素高度: {h}px，宽度: {nav_w}px")
