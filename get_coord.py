"""
坐标获取工具
运行后，点击鼠标左键即可获取当前鼠标坐标
"""
from pynput import mouse

print("=" * 50)
print("坐标获取工具")
print("=" * 50)
print("将鼠标移到目标位置，点击鼠标左键获取坐标")
print("按 Ctrl+C 退出")
print("=" * 50)


def on_click(x, y, button, pressed):
    if pressed and button == mouse.Button.left:
        print(f"坐标: ({x}, {y})")
        return True  # 继续监听


with mouse.Listener(on_click=on_click) as listener:
    listener.join()
