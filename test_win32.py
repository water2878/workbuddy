import ctypes, time
import win32gui

hwnd = ctypes.windll.user32.FindWindowW(None, '微信')
print('hwnd:', hwnd)
title = win32gui.GetWindowText(hwnd)
print('当前标题:', repr(title))

# 枚举所有子窗口
def enum_cb(hwnd, results):
    t = win32gui.GetWindowText(hwnd)
    if t:
        results.append((hwnd, t))
results = []
win32gui.EnumChildWindows(hwnd, enum_cb, results)
print(f'子窗口数量: {len(results)}')
for h, t in results[:20]:
    print(f'  hwnd={h}, text={repr(t)}')
