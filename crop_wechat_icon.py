"""
从截图中裁剪微信图标，更新 wechat_icon_sample.png 模板。

分析用户截图：任务栏区域，从左到右图标顺序为：
  ^ (展开箭头) | V(杀毒?) | 微信(绿色方块) | 云图标 | S图标 | WiFi | 声音
微信图标在截图中位于约第3个图标的位置（绿色背景的W图标）
"""
import sys
sys.path.insert(0, r'C:\Users\Lenovo\.workbuddy\skills\wechat-automation')

import pyautogui
import os
from PIL import Image
import shutil

# 截图路径
TASKBAR_IMG = r'C:\Users\Lenovo\WorkBuddy\Claw\taskbar_right.png'
# 模板保存路径
TEMPLATE_PATH = r'C:\Users\Lenovo\.workbuddy\skills\wechat-automation\assets\wechat_icon_sample.png'

def analyze_and_crop():
    """分析截图并裁剪微信图标"""
    img = Image.open(TASKBAR_IMG)
    w, h = img.size
    print(f"截图尺寸: {w} x {h}")
    
    # 实时截取任务栏，精确定位微信图标
    # 根据用户截图分析，微信图标在系统托盘区域
    # 屏幕宽1920（假设），从右边400px区域开始
    # 图标大小约为16-24px
    
    # 先保存截图供检查
    img.save(r'C:\Users\Lenovo\WorkBuddy\Claw\taskbar_for_analysis.png')
    print(f"已保存分析用截图")
    
    # 根据用户提供的截图分析：
    # 截图分辨率约279x68，微信图标（绿色）约在x=55-75的位置
    # 从用户发的那张图片截图看，微信图标在第3个位置
    
    # 在 taskbar_right.png 中搜索绿色区域
    import numpy as np
    img_array = np.array(img)
    
    print(f"图片形状: {img_array.shape}")
    
    # 查找绿色像素（微信图标特征色：绿色 #07C160 or similar）
    # R < 50, G > 150, B < 50 → 微信绿色
    r = img_array[:, :, 0]
    g = img_array[:, :, 1]
    b = img_array[:, :, 2]
    
    # 微信图标绿色掩码
    green_mask = (r < 80) & (g > 140) & (b < 80)
    green_pixels = np.where(green_mask)
    
    if len(green_pixels[0]) > 0:
        min_y = int(green_pixels[0].min())
        max_y = int(green_pixels[0].max())
        min_x = int(green_pixels[1].min())
        max_x = int(green_pixels[1].max())
        print(f"找到绿色区域: x={min_x}-{max_x}, y={min_y}-{max_y}")
        
        # 扩展一些边距
        pad = 4
        crop_x1 = max(0, min_x - pad)
        crop_y1 = max(0, min_y - pad)
        crop_x2 = min(w, max_x + pad)
        crop_y2 = min(h, max_y + pad)
        
        icon = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
        print(f"裁剪区域: ({crop_x1}, {crop_y1}, {crop_x2}, {crop_y2})")
        print(f"裁剪尺寸: {icon.size}")
        
        # 备份原模板
        if os.path.exists(TEMPLATE_PATH):
            backup = TEMPLATE_PATH.replace('.png', '_backup.png')
            shutil.copy2(TEMPLATE_PATH, backup)
            print(f"已备份原模板到: {backup}")
        
        # 保存新模板
        icon.save(TEMPLATE_PATH)
        print(f"已更新模板: {TEMPLATE_PATH}")
        
        # 同时保存一份到工作目录
        icon.save(r'C:\Users\Lenovo\WorkBuddy\Claw\wechat_icon_cropped.png')
        print(f"已保存裁剪图标到: C:\\Users\\Lenovo\\WorkBuddy\\Claw\\wechat_icon_cropped.png")
        
        return True
    else:
        print("未找到绿色区域，尝试其他方法...")
        
        # 保存各通道信息便于调试
        for i, (row, col) in enumerate(zip(green_pixels[0][:5], green_pixels[1][:5])):
            print(f"  pixel[{i}]: ({col},{row}) R={r[row,col]} G={g[row,col]} B={b[row,col]}")
        
        return False

if __name__ == '__main__':
    success = analyze_and_crop()
    if not success:
        print("\n建议手动从 taskbar_right.png 中截取微信图标")
        print("微信图标为绿色背景的W形图案")
