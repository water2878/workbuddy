"""
用 uiautomation 探测微信窗口结构
"""
import uiautomation as auto
import time

auto.uiautomation.SetGlobalSearchTimeout(3)

# 找微信主窗口
wechat = auto.WindowControl(searchDepth=1, Name='微信')
if not wechat.Exists(3):
    wechat = auto.WindowControl(searchDepth=1, ClassName='WeChatMainWndForPC')
if not wechat.Exists(3):
    # xwechat
    wechat = auto.WindowControl(searchDepth=1, ClassName='WXMainWnd')

print(f"找到窗口: {wechat.Exists(1)}")
print(f"  Name: {wechat.Name}")
print(f"  ClassName: {wechat.ClassName}")

# 深度遍历控件树，找到联系人列表
def dump_controls(ctrl, depth=0, max_depth=8):
    if depth > max_depth:
        return
    try:
        name = ctrl.Name
        ctype = ctrl.ControlTypeName
        cls = ctrl.ClassName
        rect = ctrl.BoundingRectangle
        if name or cls:
            print('  '*depth + f'[{ctype}] Name={repr(name[:30] if name else "")} Class={cls} Rect={rect}')
        for c in ctrl.GetChildren():
            dump_controls(c, depth+1, max_depth)
    except Exception as e:
        pass

print("\n=== 控件树 (深度8) ===")
dump_controls(wechat, max_depth=5)
