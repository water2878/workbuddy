import time
import ctypes
import ctypes.wintypes

# 查找并激活微信窗口
def find_and_activate_wechat():
    print("正在查找微信窗口...")
    hwnd = ctypes.windll.user32.FindWindowW(None, "微信")
    if hwnd == 0:
        hwnd = ctypes.windll.user32.FindWindowW(None, "WeChat")
    if hwnd == 0:
        print("❌ 未找到微信窗口，请先打开微信")
        return None, None
    
    print("✅ 找到微信窗口，正在激活...")
    ctypes.windll.user32.ShowWindow(hwnd, 9)  # 显示窗口
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)  # 置于前台
    time.sleep(0.8)

    # 获取窗口信息
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win = {
        'x': rect.left,
        'y': rect.top,
        'w': rect.right - rect.left,
        'h': rect.bottom - rect.top
    }
    print(f"✅ 微信窗口信息: x={win['x']}, y={win['y']}, w={win['w']}, h={win['h']}")
    return hwnd, win

if __name__ == "__main__":
    hwnd, win = find_and_activate_wechat()
    if win:
        print("\n🎉 测试成功！微信窗口已被正确识别和激活")
    else:
        print("\n❌ 测试失败！未找到微信窗口")
