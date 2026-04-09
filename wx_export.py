import time
import pyautogui
import ctypes
import ctypes.wintypes

pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = False

def find_and_activate_wechat():
    hwnd = ctypes.windll.user32.FindWindowW(None, "\u5fae\u4fe1")
    if hwnd == 0:
        hwnd = ctypes.windll.user32.FindWindowW(None, "WeChat")
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(1)
    return hwnd

hwnd = find_and_activate_wechat()

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
win_x = rect.left
win_y = rect.top
win_w = rect.right - rect.left
win_h = rect.bottom - rect.top

# 菜单在左下角弹出，每行约30px，第5行
btn_x = win_x + int(win_w * 0.04)
btn_y = win_y + int(win_h * 0.95)
# 菜单向上弹出，第1行在最下，第5行往上数5*30=150px
menu_x = btn_x + 60
menu_y = btn_y - (5 * 30)
print("Clicking menu item 5 at: %d, %d" % (menu_x, menu_y))
pyautogui.click(menu_x, menu_y)
time.sleep(1.5)

# 截图看设置页面
screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
screenshot.save(r"c:\Users\Lenovo\WorkBuddy\Claw\wechat_settings.png")
print("Screenshot saved")
