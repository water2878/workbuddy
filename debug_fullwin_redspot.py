# -*- coding: utf-8 -*-
"""用新阈值检测红点，在完整窗口图上标注验证"""
import ctypes, ctypes.wintypes, time
import numpy as np, pyautogui
from PIL import Image, ImageDraw

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
arr_left = arr[:, :lw, :]

r = arr_left[:,:,0].astype(int)
g = arr_left[:,:,1].astype(int)
b = arr_left[:,:,2].astype(int)

# 新阈值：高纯度红
mask = (r > 230) & (g < 110) & (b < 110) & ((r - g) > 130) & ((r - b) > 130)
red_pixels = np.argwhere(mask)
print(f'高纯度红像素数: {len(red_pixels)}')

if len(red_pixels) == 0:
    print('未找到红点')
    exit(0)

# 行聚类
rows = sorted(set(red_pixels[:, 0].tolist()))
clusters, cluster = [], [rows[0]]
for row in rows[1:]:
    if row - cluster[-1] <= 8:
        cluster.append(row)
    else:
        clusters.append(cluster)
        cluster = [row]
clusters.append(cluster)

badge_centers = []
for c in clusters:
    c_set = set(c)
    c_pixels = np.array([p for p in red_pixels if p[0] in c_set])
    if len(c_pixels) < 5:
        continue
    cy = int(np.mean(c_pixels[:, 0]))
    cx = int(np.mean(c_pixels[:, 1]))
    print(f'  角标: y={cy}, x={cx}, 像素={len(c_pixels)}')
    badge_centers.append((cy, cx))

# 标注
annotated = img.copy().convert('RGB')
draw = ImageDraw.Draw(annotated)
for i, (cy, cx) in enumerate(badge_centers):
    draw.ellipse([(cx-12, cy-12), (cx+12, cy+12)], outline=(0,255,0), width=2)
    draw.line([(0, cy), (lw, cy)], fill=(0,255,0), width=1)
    draw.text((lw+2, max(0,cy-8)), f'#{i+1} y={cy}', fill=(0,200,0))

annotated.save('debug_fullwin_annotated.png')
print(f'共 {len(badge_centers)} 个红点，标注图 → debug_fullwin_annotated.png')
