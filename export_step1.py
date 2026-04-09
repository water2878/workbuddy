# -*- coding: utf-8 -*-
"""
第一遍：只截取标题栏，让用户确认要导出哪些
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time
import os
import shutil
from pathlib import Path
import ctypes

import pyautogui
import win32gui
import win32con
from PIL import Image

# ============== 配置 ==============
DESKTOP = Path.home() / "Desktop"
OUTPUT_DIR = DESKTOP / "微信聊天记录_确认"
TITLE_BAR_RECT = {"left": 480, "top": 95, "width": 600, "height": 50}

# 坐标
WECHAT_ICON = (140, 1043)
CONTACT_LIST_START = (321, 270)
CONTACT_LIST_STEP = 72


def activate_wechat():
    hwnd = win32gui.FindWindow(None, "微信")
    if hwnd:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except:
            pass
        time.sleep(0.8)
        return True
    pyautogui.click(WECHAT_ICON)
    time.sleep(1.5)
    return True


def click_contact(index):
    x = CONTACT_LIST_START[0]
    y = CONTACT_LIST_START[1] + index * CONTACT_LIST_STEP
    pyautogui.click(x, y)
    time.sleep(0.5)


def get_title_screenshot():
    screenshot = pyautogui.screenshot()
    title_img = screenshot.crop((
        TITLE_BAR_RECT["left"],
        TITLE_BAR_RECT["top"],
        TITLE_BAR_RECT["left"] + TITLE_BAR_RECT["width"],
        TITLE_BAR_RECT["top"] + TITLE_BAR_RECT["height"]
    ))
    return title_img


def scan_contacts():
    """遍历所有联系人，只截标题栏"""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    
    activate_wechat()
    click_contact(0)
    time.sleep(1)
    
    max_contacts = 20
    contact_list = []  # 存储要导出的联系人
    
    for i in range(max_contacts):
        print(f"\n[{i+1}/{max_contacts}] 点击联系人...")
        
        click_contact(i)
        time.sleep(0.8)
        
        # 截取标题栏
        title_img = get_title_screenshot()
        
        # 保存
        title_path = OUTPUT_DIR / f"{i+1:02d}_标题.png"
        title_img.save(title_path)
        
        # 显示
        title_img.show()
        
        # 让用户确认
        print(f"\n  查看弹出的截图")
        print(f"  输入名称（要导出）或者直接回车（跳过）: ", end="")
        name = input().strip()
        
        if name:
            contact_list.append({"index": i, "name": name})
            print(f"  [勾选] {name}")
        else:
            print(f"  [跳过]")
        
        # 关闭图片查看器
        time.sleep(0.5)
    
    # 保存联系人列表
    list_path = OUTPUT_DIR / "_联系人列表.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        f.write("要导出的联系人列表：\n")
        f.write("="*30 + "\n")
        for item in contact_list:
            f.write(f"{item['name']}\n")
    
    print(f"\n{'='*50}")
    print(f"[完成] 共扫描 {max_contacts} 个联系人")
    print(f"       要导出: {len(contact_list)} 个")
    print(f"       位置: {OUTPUT_DIR}")
    print(f"\n下一步运行：导出完整聊天记录")
    print('='*50)
    
    return contact_list


if __name__ == "__main__":
    print("="*50)
    print("第一步：确认要导出的联系人")
    print("="*50)
    print("流程：")
    print("  1. 自动点击每个联系人")
    print("  2. 弹出标题栏截图")
    print("  3. 输入名称=要导出，回车=跳过")
    print("\n请确保微信已打开，3秒后开始...")
    time.sleep(3)
    scan_contacts()
