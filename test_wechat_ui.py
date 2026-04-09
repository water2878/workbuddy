from pywinauto import Desktop
import ctypes

desktop = Desktop(backend='uia')
hwnd = ctypes.windll.user32.FindWindowW(None, '微信')
print('hwnd:', hwnd)

try:
    wechat = desktop.window(title_re='微信|WeChat')
    print('找到微信窗口')
    children = wechat.children()
    for i, c in enumerate(children[:30]):
        try:
            t = c.window_text()
            ct = c.element_info.control_type
            print(f'  [{i}] type={ct}, text={repr(t[:40])}')
        except:
            pass
except Exception as e:
    print('错误:', e)
