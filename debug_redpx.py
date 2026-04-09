# -*- coding: utf-8 -*-
"""激活微信后截图，打印所有红色像素坐标和RGB值"""
import ctypes, ctypes.wintypes, time, pyautogui, numpy as np
from PIL import Image

hwnd = ctypes.windll.user32.FindWindowW(None, '微信') or ctypes.windll.user32.FindWindowW(None, 'WeChat')
ctypes.windll.user32.ShowWindow(hwnd, 9)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(0.8)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
wx, wy = rect.left, rect.top
ww = rect.right - rect.left
wh = rect.bottom - rect.top

img = pyautogui.screenshot(region=(wx, wy, ww, wh))
img.save('debug_wechat_full.png')

arr = np.array(img.convert('RGB'))
lw = int(ww * 0.35)

r = arr[:, :lw, 0].astype(int)
g = arr[:, :lw, 1].astype(int)
b = arr[:, :lw, 2].astype(int)
mask = (r > 150) & (g < 100) & (b < 100)
px = np.argwhere(mask)

print(f'窗口: {ww}x{wh} @ ({wx},{wy})')
print(f'红色像素数: {len(px)}')
for p in px:
    rv, gv, bv = arr[p[0], p[1], 0], arr[p[0], p[1], 1], arr[p[0], p[1], 2]
    print(f'  y={p[0]:4d}, x={p[1]:4d}, RGB=({rv},{gv},{bv})')
