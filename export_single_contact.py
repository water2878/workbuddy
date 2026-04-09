# -*- coding: utf-8 -*-
"""
导出指定微信联系人的全部聊天记录（优化版）
- 支持手动打开聊天窗口后自动检测并导出
- 或自动搜索并进入联系人聊天
- 使用 OCR 提取文字内容
- 输出为 txt + html 双格式

用法：
    python export_single_contact.py
    或修改下方 TARGET_NAME 后直接运行
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time
import os
import re
import ctypes
import ctypes.wintypes
import hashlib
from datetime import datetime
from pathlib import Path

import pyautogui
import pyperclip
from PIL import Image

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = False

# ============================================================
# ★ 配置区 - 按需修改
# ============================================================
TARGET_NAME   = "AiLy 李15502540306"   # 要搜索的联系人名称（支持模糊）
TARGET_PHONE  = "15502540306"           # 备用手机号搜索

DESKTOP       = Path.home() / "Desktop"
OUTPUT_DIR    = DESKTOP / f"微信导出_{TARGET_NAME}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

SCROLL_PAUSE  = 0.8    # 每次滚动后等待（秒）
MAX_SCROLLS   = 500    # 最多向上滚动多少次
CHAT_SCROLL_STEP = 10  # 每次向上滚动几格

# 模式选择：
#   'auto'   - 自动搜索并进入联系人（默认）
#   'manual' - 等待用户手动打开聊天窗口后自动检测
MODE = 'auto'

# OCR 引擎：'winrt'（内置，推荐）或 'skip'（只截图）
OCR_ENGINE = 'winrt'
# ============================================================


def find_wechat_window():
    """找到并激活微信窗口，返回 (hwnd, win_rect)"""
    for title in ["微信", "WeChat"]:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            break
    if not hwnd:
        print("❌ 未找到微信窗口，请先打开微信！")
        return None, None

    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)

    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win = dict(x=rect.left, y=rect.top,
               w=rect.right - rect.left, h=rect.bottom - rect.top)
    print(f"✅ 微信窗口: {win['w']}x{win['h']} at ({win['x']}, {win['y']})")
    return hwnd, win


def capture_window(win):
    """截取微信窗口画面"""
    return pyautogui.screenshot(region=(win['x'], win['y'], win['w'], win['h']))


def find_search_box(win, screenshot):
    """用颜色/位置特征找搜索框的大致位置"""
    # 搜索框通常在顶部居中偏左，背景略深
    # 尝试在顶部 10% 区域找灰色/深色矩形
    w, h = screenshot.size
    search_y_start = int(h * 0.02)
    search_y_end = int(h * 0.08)
    
    # 简单策略：返回估算位置（比例）
    cx = w // 2
    cy = (search_y_start + search_y_end) // 2
    # 搜索框通常在左侧 20-35% 区域
    return int(w * 0.18), search_y_start + 15


def find_contact_in_list(win, screenshot, keyword):
    """在搜索结果列表中查找联系人并点击"""
    w, h = screenshot.size
    
    # 搜索结果通常在搜索框下方，y 约 10%-25%
    result_y_start = int(h * 0.10)
    result_y_end = int(h * 0.30)
    
    # 联系人列表项通常在左侧，x 约 5%-25%
    # 点击第一个搜索结果
    click_x = int(w * 0.15)
    click_y = int((result_y_start + result_y_end) / 2)
    
    return click_x, click_y


def auto_search_and_open(win, keyword):
    """使用 Ctrl+F 搜索并打开联系人"""
    w, h = win['w'], win['h']
    
    print(f"🔍 Ctrl+F 搜索联系人: {keyword}")
    
    # 1. 按 Ctrl+F 打开搜索框
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.8)
    
    # 2. 输入关键词
    pyperclip.copy(keyword)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(1.0)
    
    # 3. 按 Enter 进入第一个搜索结果
    pyautogui.press('enter')
    time.sleep(1.5)
    
    # 4. 检查是否成功进入聊天
    screenshot = pyautogui.screenshot()
    check_x = win['x'] + int(w * 0.6)
    check_y = win['y'] + int(h * 0.5)
    pixel = screenshot.getpixel((check_x, check_y))
    print(f"  进入检测像素: {pixel}")
    
    return True


def detect_current_contact(win, screenshot):
    """检测当前打开的聊天窗口顶部显示的联系人名称"""
    w, h = screenshot.size
    
    # 微信联系人名称显示在顶部中间区域
    # 约 x: 30%-50%, y: 2%-6%
    name_x_start = int(w * 0.30)
    name_x_end = int(w * 0.55)
    name_y_start = int(h * 0.02)
    name_y_end = int(h * 0.06)
    
    # 截取这个区域用于 OCR
    name_region = screenshot.crop((name_x_start, name_y_start, name_x_end, name_y_end))
    
    # 临时保存用于调试
    # name_region.save(f"debug_name_region_{int(time.time())}.png")
    
    # 使用 WinRT OCR 识别联系人名称
    try:
        import asyncio
        import winsdk.windows.media.ocr as winrt_ocr
        import winsdk.windows.globalization as globalization
        import winsdk.windows.graphics.imaging as imaging
        import winsdk.windows.storage.streams as streams
        import io as _io
        
        async def do_ocr():
            buf = _io.BytesIO()
            name_region.save(buf, format="PNG")
            buf.seek(0)
            img_bytes = buf.read()
            
            data_writer = streams.DataWriter()
            data_writer.write_bytes(img_bytes)
            img_stream = streams.InMemoryRandomAccessStream()
            await img_stream.write_async(data_writer.detach_buffer())
            img_stream.seek(0)
            
            decoder = await imaging.BitmapDecoder.create_async(img_stream)
            soft_bmp = await decoder.get_software_bitmap_async()
            
            engine = winrt_ocr.OcrEngine.try_create_from_language(globalization.Language("zh-Hans"))
            if engine is None:
                engine = winrt_ocr.OcrEngine.try_create_from_user_profile_languages()
            if engine is None:
                return ""
            
            result = await engine.recognize_async(soft_bmp)
            texts = [line.text for line in result.lines]
            return "".join(texts)
        
        contact_name = asyncio.run(do_ocr())
        return contact_name.strip()
    except Exception as e:
        print(f"  OCR 识别联系人名称失败: {e}")
        return ""


def wait_for_target_contact(win, target_name, timeout=30):
    """等待用户打开目标联系人聊天窗口"""
    print(f"⏳ 等待打开聊天窗口: {target_name}")
    print(f"   请手动点击打开与 \"{target_name}\" 的聊天窗口...")
    print(f"   检测倒计时: {timeout} 秒")
    
    start_time = time.time()
    last_name = ""
    
    while time.time() - start_time < timeout:
        screenshot = pyautogui.screenshot()
        current_name = detect_current_contact(win, screenshot)
        
        if current_name and current_name != last_name:
            print(f"  检测到当前联系人: {current_name}")
            last_name = current_name
            
            # 检查是否匹配目标
            if target_name in current_name or current_name in target_name:
                print(f"  ✅ 匹配成功！")
                return True
        
        time.sleep(2)
    
    # 超时后也尝试继续
    print("  ⏰ 超时未检测到目标联系人，将尝试继续...")
    return True


def get_chat_region(win):
    """返回聊天内容区域 (left, top, width, height)"""
    left  = win['x'] + int(win['w'] * 0.27)
    top   = win['y'] + int(win['h'] * 0.07)
    w     = int(win['w'] * 0.70)
    h     = int(win['h'] * 0.82)
    return left, top, w, h


def img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()


def ocr_image(img: Image.Image) -> list:
    """对单张截图做 OCR，返回文字块列表"""
    if OCR_ENGINE == 'winrt':
        return _ocr_winrt(img)
    return []


def _ocr_winrt(img: Image.Image) -> list:
    """使用 Windows 内置 WinRT OCR"""
    try:
        import asyncio
        import winsdk.windows.media.ocr as winrt_ocr
        import winsdk.windows.globalization as globalization
        import winsdk.windows.graphics.imaging as imaging
        import winsdk.windows.storage.streams as streams
        import io as _io
        
        async def do_ocr():
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            img_bytes = buf.read()
            
            data_writer = streams.DataWriter()
            data_writer.write_bytes(img_bytes)
            img_stream = streams.InMemoryRandomAccessStream()
            await img_stream.write_async(data_writer.detach_buffer())
            img_stream.seek(0)
            
            decoder = await imaging.BitmapDecoder.create_async(img_stream)
            soft_bmp = await decoder.get_software_bitmap_async()
            
            engine = winrt_ocr.OcrEngine.try_create_from_language(globalization.Language("zh-Hans"))
            if engine is None:
                engine = winrt_ocr.OcrEngine.try_create_from_user_profile_languages()
            if engine is None:
                return []
            
            result = await engine.recognize_async(soft_bmp)
            blocks = []
            for line in result.lines:
                text = line.text.strip()
                if text:
                    blocks.append({"text": text, "y": len(blocks)})
            return blocks
        
        return asyncio.run(do_ocr())
    except Exception as e:
        print(f"  ⚠️ WinRT OCR 出错: {e}")
        return []


def parse_messages_from_blocks(blocks, img_index):
    """从 OCR 文字块中启发式解析消息"""
    messages = []
    current_time = None
    
    time_pattern = re.compile(r'^(\d{1,2}:\d{2})$|^(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2})$')
    
    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            continue
        
        # 检查是否是时间戳
        if time_pattern.match(text) or ("年" in text and "月" in text):
            current_time = text
        else:
            if current_time or text:
                messages.append({
                    "time": current_time or "",
                    "text": text,
                    "page": img_index
                })
    
    return messages


def deduplicate_messages(messages):
    """去掉跨页重复消息"""
    if not messages:
        return []
    
    # 按文本内容去重（相邻重复）
    deduped = []
    prev_text = ""
    for msg in messages:
        if msg["text"] != prev_text:
            deduped.append(msg)
            prev_text = msg["text"]
    
    return deduped


def save_txt(messages, contact_name, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"微信聊天记录 - {contact_name}\n")
        f.write("=" * 50 + "\n\n")
        for msg in messages:
            if msg["time"]:
                f.write(f"\n[{msg['time']}]\n")
            f.write(msg["text"] + "\n")


def save_html(messages, contact_name, path):
    rows = []
    for msg in messages:
        time_str = f'<span class="time">{msg["time"]}</span>' if msg["time"] else ""
        rows.append(f'<div class="msg">{time_str}<div class="text">{msg["text"]}</div></div>')
    
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>微信聊天记录 - {contact_name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; 
       background: #f5f5f5; margin: 0; padding: 20px; }}
.container {{ max-width: 800px; margin: 0 auto; background: #fff; 
             border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; }}
h1 {{ color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
.msg {{ margin: 8px 0; padding: 8px; border-radius: 4px; }}
.time {{ color: #999; font-size: 12px; margin-right: 8px; }}
.text {{ color: #333; line-height: 1.6; }}
</style></head>
<body><div class="container">
<h1>💬 {contact_name}</h1>
{''.join(rows)}
</div></body></html>"""
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def save_combined_image(screenshots, path):
    if not screenshots:
        return
    widths, heights = zip(*(s.size for s in screenshots))
    total_width = max(widths)
    total_height = sum(heights)
    combined = Image.new('RGB', (total_width, total_height))
    y_offset = 0
    for screenshot in screenshots:
        combined.paste(screenshot, (0, y_offset))
        y_offset += screenshot.size[1]
    combined.save(path)


def scroll_to_top_and_capture(win, output_dir: Path):
    """从当前聊天窗口顶部开始，逐页向下截图"""
    left, top, w, h = get_chat_region(win)
    cx, cy = left + w // 2, top + h // 2
    
    # 点击聊天区域获取焦点
    pyautogui.click(cx, cy)
    time.sleep(0.4)
    
    # 滚到最顶部
    print("⏫ 正在滚动到最顶部...")
    pyautogui.hotkey('ctrl', 'Home')
    time.sleep(2.0)
    
    screenshots = []
    prev_hash = ""
    scroll_count = 0
    
    print(f"📸 开始逐页截图（最多 {MAX_SCROLLS} 页）...")
    
    while scroll_count < MAX_SCROLLS:
        # 截取聊天区域
        screenshot = pyautogui.screenshot(region=(left, top, w, h))
        screenshots.append(screenshot)
        
        curr_hash = img_hash(screenshot)
        print(f"  第 {len(screenshots)} 页: {w}x{h} (hash: {curr_hash[:8]}...)")
        
        # 检查是否滚动到底了（和上一张相同）
        if curr_hash == prev_hash and scroll_count > 5:
            print("  ✅ 已到达最早消息或重复页面")
            break
        
        prev_hash = curr_hash
        
        # 向上滚动
        for _ in range(CHAT_SCROLL_STEP):
            pyautogui.scroll(300)
        time.sleep(SCROLL_PAUSE)
        scroll_count += 1
    
    print(f"  📊 共截取 {len(screenshots)} 页")
    return screenshots


def main():
    print("=" * 50)
    print("  微信聊天记录导出工具（优化版）")
    print(f"  目标联系人: {TARGET_NAME}")
    print(f"  模式: {'手动（等待打开窗口）' if MODE == 'manual' else '自动搜索'}")
    print("=" * 50)
    
    # 1. 找到微信窗口
    hwnd, win = find_wechat_window()
    if not win:
        return
    
    # 2. 进入目标联系人聊天
    if MODE == 'auto':
        # 自动搜索模式
        success = auto_search_and_open(win, TARGET_NAME)
        if not success:
            print("❌ 自动搜索失败，请使用手动模式")
            return
    else:
        # 手动模式：等待用户打开窗口
        wait_for_target_contact(win, TARGET_NAME, timeout=30)
    
    # 3. 等待一下让界面稳定
    time.sleep(2)
    
    # 4. 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = OUTPUT_DIR / "raw_screenshots"
    raw_dir.mkdir(exist_ok=True)
    
    # 5. 截图并滚动捕获
    screenshots = scroll_to_top_and_capture(win, OUTPUT_DIR)
    
    # 6. 保存原始截图
    print("💾 保存截图...")
    for i, shot in enumerate(screenshots):
        shot.save(raw_dir / f"page_{i+1:04d}.png")
    
    # 7. OCR 识别并解析消息
    print("🔤 OCR 识别文字...")
    all_messages = []
    for i, shot in enumerate(screenshots):
        if i % 10 == 0:
            print(f"  识别进度: {i+1}/{len(screenshots)}")
        blocks = ocr_image(shot)
        msgs = parse_messages_from_blocks(blocks, i)
        all_messages.extend(msgs)
    
    print(f"  共识别 {len(all_messages)} 条消息")
    
    # 8. 去重
    all_messages = deduplicate_messages(all_messages)
    print(f"  去重后 {len(all_messages)} 条消息")
    
    # 9. 保存结果
    print("📁 保存文件...")
    save_txt(all_messages, TARGET_NAME, OUTPUT_DIR / f"{TARGET_NAME}_聊天记录.txt")
    save_html(all_messages, TARGET_NAME, OUTPUT_DIR / f"{TARGET_NAME}_聊天记录.html")
    
    # 10. 保存完整长图
    # save_combined_image(screenshots, OUTPUT_DIR / f"{TARGET_NAME}_完整长图.png")
    
    print("\n" + "=" * 50)
    print("✅ 导出完成！")
    print(f"📂 输出目录: {OUTPUT_DIR}")
    print("=" * 50)
    
    # 打开输出目录
    os.startfile(OUTPUT_DIR)


if __name__ == "__main__":
    main()
