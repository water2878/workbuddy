# -*- coding: utf-8 -*-
"""
逐一点击左侧导航栏不同高度，截图查看切换到了哪个页面
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
wx = rect.left
wy = rect.top
ww = rect.right  - rect.left
wh = rect.bottom - rect.top
print(f"窗口: x={wx} y={wy} w={ww} h={wh}")

nav_x = wx + int(ww * 0.04)  # 导航栏中心 x

# 依次点击每个比例位置，截全窗口截图
# 前4个 (10%~31%) 均显示聊天列表，继续向下测试
ratios = [0.38, 0.45, 0.52, 0.59]
labels = ["38pct", "45pct", "52pct", "59pct"]

for ratio, label in zip(ratios, labels):
    nav_y = wy + int(wh * ratio)
    print(f"点击 ({nav_x}, {nav_y}) 比例={ratio}")
    pyautogui.click(nav_x, nav_y)
    time.sleep(1.5)
    shot = pyautogui.screenshot(region=(wx, wy, ww, wh))
    out = f"C:/Users/Lenovo/WorkBuddy/Claw/nav_click2_{label}.png"
    shot.save(out)
    print(f"  已保存: {out}")

print("完成，请查看截图确认通讯录位置")
