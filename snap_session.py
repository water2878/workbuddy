import ctypes, ctypes.wintypes, time
import pyautogui

hwnd = 0
for title in ["微信", "WeChat"]:
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd:
        break

if not hwnd:
    print("未找到微信窗口")
    exit(1)

ctypes.windll.user32.ShowWindow(hwnd, 9)
time.sleep(0.4)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
x, y = rect.left, rect.top
w = rect.right - rect.left
h = rect.bottom - rect.top
print(f"微信窗口: x={x}, y={y}, w={w}, h={h}")

crop_w = int(w * 0.65)
screenshot = pyautogui.screenshot(region=(x, y, crop_w, h))
out = r"C:\Users\Lenovo\WorkBuddy\Claw\session_list_snapshot.png"
screenshot.save(out)
print(f"已保存: {out}")
