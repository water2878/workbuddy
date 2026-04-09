# -*- coding: utf-8 -*-
"""截取微信窗口，标注关键坐标，帮助调试"""
import ctypes, ctypes.wintypes, time
import pyautogui
from PIL import Image, ImageDraw, ImageFont

for title in ["微信", "WeChat"]:
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd: break

if not hwnd:
    print("未找到微信窗口")
    exit(1)

ctypes.windll.user32.ShowWindow(hwnd, 9)
time.sleep(0.5)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(0.8)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
x, y = rect.left, rect.top
w, h = rect.right - x, rect.bottom - y
print(f"微信窗口: x={x} y={y} w={w} h={h}")

img = pyautogui.screenshot(region=(x, y, w, h))
draw = ImageDraw.Draw(img)

# 标注搜索框位置（多个候选）
candidates = [
    ("搜索框_旧", int(w*0.16), int(h*0.04), "red"),
    ("搜索框_候选1", int(w*0.30), int(h*0.04), "blue"),
    ("搜索框_候选2", int(w*0.16), int(h*0.06), "green"),
    ("联系人列表中部", int(w*0.16), int(h*0.17), "orange"),
]

for label, cx, cy in [(c[0], c[1], c[2]) for c in candidates]:
    color = [c[3] for c in candidates if c[0]==label][0]
    draw.ellipse([cx-8, cy-8, cx+8, cy+8], outline=color, width=3)
    draw.text((cx+10, cy-8), label, fill=color)

out = r"C:\Users\Lenovo\Desktop\wechat_debug.png"
img.save(out)
print(f"已保存截图: {out}")
img.show()
