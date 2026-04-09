import ctypes, ctypes.wintypes, time, pyautogui
pyautogui.FAILSAFE = False

hwnd = ctypes.windll.user32.FindWindowW(None, '微信')
ctypes.windll.user32.ShowWindow(hwnd, 9)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(1)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
x,y,w,h = rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top
print(f"微信窗口: x={x}, y={y}, w={w}, h={h}")

img = pyautogui.screenshot(region=(x,y,w,h))
img.save(r'c:\Users\Lenovo\WorkBuddy\Claw\wechat_now.png')
print("截图已保存: wechat_now.png")
