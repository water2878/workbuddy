"""
测试新版微信(Qt架构)能否通过uiautomation获取控件
"""
import uiautomation as auto
import ctypes, time

# 激活微信
hwnd = ctypes.windll.user32.FindWindowW(None, '微信')
ctypes.windll.user32.ShowWindow(hwnd, 9)
ctypes.windll.user32.SetForegroundWindow(hwnd)
time.sleep(1)

print("=== 尝试各种ClassName ===")

# 尝试旧版
for cls in ['WeChatMainWndForPC', 'Qt51514QWindowIcon', 'WXMainWnd', '']:
    try:
        if cls:
            w = auto.WindowControl(searchDepth=1, ClassName=cls)
        else:
            w = auto.WindowControl(searchDepth=1, Name='微信')
        if w.Exists(1):
            print(f"  找到: ClassName={cls}, Name={w.Name}")
            # 找会话列表
            try:
                lst = w.ListControl(Name='会话')
                if lst.Exists(2):
                    print(f"    ✅ 找到会话列表!")
                    items = lst.GetChildren()
                    print(f"    会话数量: {len(items)}")
                    for i, item in enumerate(items[:5]):
                        print(f"    [{i}] {repr(item.Name[:50])}")
            except Exception as e:
                print(f"    ❌ 找会话列表失败: {e}")
    except Exception as e:
        print(f"  ClassName={cls} 错误: {e}")

# 搜索所有顶级窗口
print("\n=== 所有顶级窗口 ===")
for w in auto.GetRootControl().GetChildren():
    try:
        if w.Name:
            print(f"  Name={repr(w.Name[:40])}, Class={w.ClassName}")
    except:
        pass
