# -*- coding: utf-8 -*-
"""
调试红点识别：截会话列表，找出每个红点的 Y 坐标，
并把红点所在行的「联系人名区域」单独截图保存，
方便肉眼验证 OCR 截的是不是正确的那一行。
"""
import ctypes, ctypes.wintypes, time
import numpy as np
import pyautogui
from PIL import Image, ImageDraw

# ── 找微信窗口 ──────────────────────────────────────
hwnd = 0
for title in ["微信", "WeChat"]:
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd: break

if not hwnd:
    print("未找到微信窗口")
    exit(1)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
win = dict(x=rect.left, y=rect.top,
           w=rect.right - rect.left,
           h=rect.bottom - rect.top)
print(f"窗口: {win['w']}x{win['h']} @ ({win['x']},{win['y']})")

# ── 截会话列表 ──────────────────────────────────────
lx = win['x']
ly = win['y'] + int(win['h'] * 0.08)
lw = int(win['w'] * 0.22)   # 只截头像+昵称+红点
lh = int(win['h'] * 0.85)
session_img = pyautogui.screenshot(region=(lx, ly, lw, lh))
session_img.save("debug_session_list.png")
print(f"会话列表截图: {lw}x{lh}")

# ── 找红点 ──────────────────────────────────────────
arr = np.array(session_img.convert("RGB"))
r = arr[:,:,0].astype(int)
g = arr[:,:,1].astype(int)
b = arr[:,:,2].astype(int)
mask = (r > 180) & (g < 80) & (b < 80)
red_rows = np.where(mask.any(axis=1))[0]

if len(red_rows) == 0:
    print("未找到红点")
    exit(0)

# 聚类
clusters, cluster = [], [red_rows[0]]
for row in red_rows[1:]:
    if row - cluster[-1] <= 15:
        cluster.append(row)
    else:
        clusters.append(cluster)
        cluster = [row]
clusters.append(cluster)
red_y_list = [int(np.mean(c)) for c in clusters]
print(f"找到 {len(red_y_list)} 个红点，Y坐标: {red_y_list}")

# ── 把每个红点行截图保存 + 在总图上标注 ────────────────
img_w, img_h = session_img.size
annotated = session_img.copy().convert("RGB")
draw = ImageDraw.Draw(annotated)

for i, uy in enumerate(red_y_list):
    # 标注红点位置（横线）
    draw.line([(0, uy), (img_w, uy)], fill=(255, 0, 0), width=2)
    draw.text((2, max(0, uy - 14)), f"#{i+1} y={uy}", fill=(255, 0, 0))

    # 截取联系人名区域
    row_top    = max(0, uy - 18)
    row_bottom = min(img_h, uy + 18)
    name_left  = int(img_w * 0.25)
    name_right = int(img_w * 0.85)

    row_img = session_img.crop((name_left, row_top, name_right, row_bottom))
    fname = f"debug_row_{i+1}_y{uy}.png"
    row_img.save(fname)
    print(f"  红点#{i+1}: y={uy}, 行图已保存 → {fname}  (裁剪区域: x={name_left}~{name_right}, y={row_top}~{row_bottom})")

annotated.save("debug_session_annotated.png")
print("标注图已保存 → debug_session_annotated.png")
