# -*- coding: utf-8 -*-
"""测试到底检测是否有效"""
import ctypes, ctypes.wintypes, time, hashlib
import pyautogui, numpy as np
from PIL import Image

pyautogui.FAILSAFE = False

hwnd = 0
for t in ['微信', 'WeChat']:
    hwnd = ctypes.windll.user32.FindWindowW(None, t)
    if hwnd: break

ctypes.windll.user32.ShowWindow(hwnd, 9)
time.sleep(0.5)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(0.8)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
win = dict(x=rect.left, y=rect.top,
           w=rect.right-rect.left, h=rect.bottom-rect.top)
print(f"窗口: {win}")

left = win['x'] + int(win['w'] * 0.07)
top  = win['y'] + int(win['h'] * 0.10)
w    = int(win['w'] * 0.20)
h    = int(win['h'] * 0.85)
cx, cy = left + w//2, top + h//2

print("请手动把微信通讯录滚到底部，5秒后开始测试...")
time.sleep(5)

# 连续截5张，每次滚10格
hashes_full   = []
hashes_bottom = []

for i in range(6):
    shot = pyautogui.screenshot(region=(left, top, w, h))
    shot.save(f'bottom_test_{i}.png')
    arr = np.array(shot)

    fh = hashlib.md5(arr.tobytes()).hexdigest()
    bh = hashlib.md5(arr[h*2//3:].tobytes()).hexdigest()
    hashes_full.append(fh)
    hashes_bottom.append(bh)

    print(f"  第{i+1}张 | 全页:{fh[:10]} | 底部:{bh[:10]}")

    # 继续滚
    pyautogui.moveTo(cx, cy)
    for _ in range(10):
        pyautogui.scroll(-10)
        time.sleep(0.01)
    time.sleep(0.25)

print()
print("全页哈希全部相同:", len(set(hashes_full)) == 1)
print("底部哈希全部相同:", len(set(hashes_bottom)) == 1)
print("全页不同的数量:", len(set(hashes_full)))
print("底部不同的数量:", len(set(hashes_bottom)))
