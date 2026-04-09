"""
测试：点击联系人后获取聊天标题
"""
import ctypes, ctypes.wintypes, time
import pyautogui
from pywinauto import Desktop

pyautogui.FAILSAFE = False

def get_wechat_win():
    hwnd = ctypes.windll.user32.FindWindowW(None, '微信')
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, {'x':rect.left,'y':rect.top,'w':rect.right-rect.left,'h':rect.bottom-rect.top}

hwnd, win = get_wechat_win()
print(f"窗口: {win}")

# 尝试用 uia 深层查找文本
desktop = Desktop(backend='uia')
wechat = desktop.window(title_re='微信|WeChat')

def find_all_texts(ctrl, depth=0, max_depth=6):
    if depth > max_depth:
        return
    try:
        t = ctrl.window_text()
        ct = ctrl.element_info.control_type
        if t and len(t.strip()) > 0:
            print('  ' * depth + f'[{ct}] {repr(t[:50])}')
    except:
        pass
    try:
        for child in ctrl.children():
            find_all_texts(child, depth+1, max_depth)
    except:
        pass

print("\n遍历所有文本控件 (最多6层):")
find_all_texts(wechat, max_depth=4)
