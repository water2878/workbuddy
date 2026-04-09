# -*- coding: utf-8 -*-
"""
遍历微信聊天记录 - 按键确认版
- 点击联系人 -> 显示名称 -> 按Y导出/N跳过
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
import mss
import numpy as np

# ============== 配置 ==============
DESKTOP = Path.home() / "Desktop"
OUTPUT_DIR = DESKTOP / "微信聊天记录_导出"
SCROLL_TIMES = 30
SCROLL_INTERVAL = 0.5

# ============== 坐标 ==============
WECHAT_ICON = (140, 1043)
CONTACT_LIST_START = (321, 270)
CONTACT_LIST_STEP = 72
TITLE_BAR_RECT = {"left": 480, "top": 95, "width": 600, "height": 50}


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


def scroll_chat():
    pyautogui.click(700, 500)
    time.sleep(0.2)
    pyautogui.scroll(800)
    time.sleep(SCROLL_INTERVAL)


def get_title_screenshot():
    """截取标题栏保存到文件"""
    screenshot = pyautogui.screenshot()
    title_img = screenshot.crop((
        TITLE_BAR_RECT["left"],
        TITLE_BAR_RECT["top"],
        TITLE_BAR_RECT["left"] + TITLE_BAR_RECT["width"],
        TITLE_BAR_RECT["top"] + TITLE_BAR_RECT["height"]
    ))
    return title_img


def capture_and_merge(contact_name, output_subdir):
    screenshots = []
    
    for i in range(SCROLL_TIMES):
        screenshot = pyautogui.screenshot()
        chat_area = screenshot.crop((480, 120, 1900, 1040))
        
        filename = f"{i+1:03d}.png"
        filepath = output_subdir / filename
        chat_area.save(filepath)
        screenshots.append(filepath)
        
        scroll_chat()
        
        if (i + 1) % 10 == 0:
            print(f"  截取 {i+1}/{SCROLL_TIMES}...")
    
    if screenshots:
        images = [Image.open(s) for s in screenshots]
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        
        merged = Image.new("RGB", (max_width, total_height), (255, 255, 255))
        y = 0
        for img in images:
            if img.width != max_width:
                ratio = max_width / img.width
                new_h = int(img.height * ratio)
                img = img.resize((max_width, new_h), Image.LANCZOS)
            merged.paste(img, (0, y))
            y += img.height
        
        merge_path = output_subdir / f"完整聊天记录_{contact_name}.png"
        merged.save(merge_path)
        print(f"  [已保存] {merge_path.name}")


def export_all_chats():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    
    activate_wechat()
    click_contact(0)
    time.sleep(1)
    
    max_contacts = 20
    exported = 0
    skipped = 0
    
    for i in range(max_contacts):
        print(f"\n[{i+1}/{max_contacts}] 点击联系人...")
        
        click_contact(i)
        time.sleep(0.8)
        
        # 截取标题栏
        title_img = get_title_screenshot()
        title_path = OUTPUT_DIR / "_temp_title.png"
        title_img.save(title_path)
        
        # 显示标题栏截图
        title_img.show()
        
        # 获取名称（用户手动输入或从截图判断）
        print(f"\n  请查看弹出的标题栏截图")
        print(f"  输入联系人名称（或回车跳过）: ", end="")
        contact_name = input().strip()
        
        if not contact_name:
            print("  [跳过]")
            skipped += 1
            continue
        
        # 询问是否导出
        print(f"  联系人: {contact_name}")
        print(f"  按 Y 导出聊天记录，按 N 跳过: ", end="")
        choice = input().strip().upper()
        
        if choice != "Y":
            print("  [跳过]")
            skipped += 1
            continue
        
        safe_name = contact_name[:20].replace("/", "-").replace("\\", "-")
        output_subdir = OUTPUT_DIR / safe_name
        output_subdir.mkdir(parents=True)
        
        print(f"  截取中...")
        capture_and_merge(contact_name, output_subdir)
        
        exported += 1
        print(f"  [完成] {contact_name}")
    
    # 清理临时文件
    temp_title = OUTPUT_DIR / "_temp_title.png"
    if temp_title.exists():
        temp_title.unlink()
    
    print(f"\n{'='*50}")
    print(f"[完成] 共处理 {max_contacts} 个")
    print(f"       导出: {exported} 个")
    print(f"       跳过: {skipped} 个")
    print(f"       位置: {OUTPUT_DIR}")
    print('='*50)


if __name__ == "__main__":
    print("="*50)
    print("微信聊天记录导出（按键确认版）")
    print("="*50)
    print("流程：")
    print("  1. 自动点击联系人")
    print("  2. 弹出标题栏截图")
    print("  3. 输入名称 + 按Y确认导出")
    print("\n请确保微信已打开，3秒后开始...")
    time.sleep(3)
    export_all_chats()
