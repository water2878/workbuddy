import ctypes, ctypes.wintypes, time
hwnd = 0
for t in ['微信','WeChat']:
    hwnd = ctypes.windll.user32.FindWindowW(None, t)
    if hwnd: break
if hwnd:
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.3)
    ctypes.windll.user32.MoveWindow(hwnd, 100, 100, 1108, 706, True)
    time.sleep(0.3)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print(f'窗口位置: {rect.left},{rect.top} 大小: {rect.right-rect.left}x{rect.bottom-rect.top}')
else:
    print('未找到微信')
