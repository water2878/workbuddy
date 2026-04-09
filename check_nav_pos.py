import pyautogui, time, win32gui
from PIL import Image, ImageDraw

def get_wechat_win():
    hwnd = win32gui.FindWindow('WeChatMainWndForPC', None)
    if not hwnd:
        print('未找到微信窗口')
        return None
    r = win32gui.GetWindowRect(hwnd)
    return {'x': r[0], 'y': r[1], 'w': r[2]-r[0], 'h': r[3]-r[1]}

win = get_wechat_win()
if not win:
    exit(1)

print(f'微信窗口: {win}')
print()

for ratio in [0.10, 0.17, 0.24, 0.31, 0.38, 0.45, 0.52, 0.59, 0.65, 0.72]:
    nav_x = win['x'] + int(win['w'] * 0.04)
    nav_y = win['y'] + int(win['h'] * ratio)
    print(f'  ratio={ratio:.2f}  -> 绝对坐标 ({nav_x}, {nav_y})')

time.sleep(0.3)
img = pyautogui.screenshot(region=(win['x'], win['y'], win['w'], win['h']))
draw = ImageDraw.Draw(img)

ratios = [0.10, 0.17, 0.24, 0.31, 0.38, 0.45, 0.52, 0.59, 0.65, 0.72]
for ratio in ratios:
    nav_x_rel = int(win['w'] * 0.04)
    nav_y_rel = int(win['h'] * ratio)
    color = 'red' if ratio == 0.45 else 'cyan'
    draw.ellipse([nav_x_rel-8, nav_y_rel-8, nav_x_rel+8, nav_y_rel+8], fill=color, outline='white')
    draw.text((nav_x_rel+12, nav_y_rel-8), f'{int(ratio*100)}%', fill=color)

# 特别标出左侧导航栏区域
draw.rectangle([0, 0, int(win['w']*0.08), win['h']], outline='yellow', width=2)

img.save('wechat_nav_positions.png')
print('\n已保存 wechat_nav_positions.png')
