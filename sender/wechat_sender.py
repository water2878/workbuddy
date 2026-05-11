"""
微信消息发送模块 — WeChat UI 自动化
从旧项目迁移，功能完全一致。
支持：文字消息（分段）、图片发送、文件发送
"""
import subprocess
import time
import random
import io
import os
import struct
import ctypes
import threading
from typing import Optional

import pyautogui
import pyperclip
import win32clipboard
import win32con
from pywinauto import keyboard
from PIL import Image

# 输入框坐标（可通过校准更新）
INPUT_BOX = (1437, 963)
WECHAT_ICON = (1850, 1050)

# 联系人映射
try:
    from contact_mapping import get_search_name, confirm_before_send
except ImportError:
    def get_search_name(name):
        return name
    def confirm_before_send(name):
        return name, True

# 全局变量记录当前聊天状态
_current_chat_contact: Optional[str] = None


def is_wechat_foreground() -> bool:
    """检查微信窗口是否在前台"""
    try:
        import win32gui
        import win32process
        import psutil

        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd == 0:
            return False

        window_title = win32gui.GetWindowText(foreground_hwnd)
        if window_title in ('微信', 'WeChat'):
            try:
                _, pid = win32process.GetWindowThreadProcessId(foreground_hwnd)
                process = psutil.Process(pid)
                if process.name().lower() in ('wechat.exe', 'weixin.exe'):
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def force_wechat_foreground() -> bool:
    """强制将微信窗口带到最前面"""
    try:
        import win32gui
        import win32con

        handles = []
        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title in ('微信', 'WeChat'):
                    extra.append(hwnd)
            return True

        win32gui.EnumWindows(callback, handles)

        if handles:
            hwnd = handles[0]
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception as e:
        print(f"强制前台失败: {e}")
    return False


def ensure_wechat_focused() -> bool:
    """确保微信窗口在最前面并获取焦点"""
    if force_wechat_foreground():
        time.sleep(0.3)
        if is_wechat_foreground():
            return True

    # 备用：点击任务栏图标
    try:
        import cv2
        import numpy as np
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(script_dir, "assets", "wechat_icon_sample.png"),
            os.path.join(script_dir, "wechat_icon_sample.png"),
            os.path.join(os.path.dirname(script_dir), "wechat_icon_sample.png"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                template = cv2.imread(path)
                if template is not None:
                    h, w = template.shape[:2]
                    screen_w, screen_h = pyautogui.size()
                    taskbar_top = screen_h - 60
                    screenshot = pyautogui.screenshot()
                    taskbar_img = screenshot.crop((0, taskbar_top, screen_w, screen_h))
                    taskbar = cv2.cvtColor(np.array(taskbar_img), cv2.COLOR_RGB2BGR)
                    result = cv2.matchTemplate(taskbar, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    if max_val > 0.8:
                        cx = max_loc[0] + w // 2
                        cy = taskbar_top + max_loc[1] + h // 2
                        pyautogui.click(cx, cy)
                        time.sleep(0.5)
                        return True
    except Exception:
        pass

    # 最后手段：固定坐标
    pyautogui.click(*WECHAT_ICON)
    time.sleep(0.5)
    return True


def _copy_text(text: str):
    """复制文字到剪贴板（win32clipboard，确保中文不乱码）"""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(
            win32con.CF_UNICODETEXT,
            text
        )
    finally:
        win32clipboard.CloseClipboard()


def search_contact(name_or_alias: str):
    """搜索并进入联系人聊天窗口 - 优化版，减少延迟"""
    search_name = get_search_name(name_or_alias)
    if search_name != name_or_alias:
        print(f"  名称映射: {name_or_alias} -> {search_name}")

    keyboard.send_keys('^f')
    time.sleep(0.15)
    _copy_text(search_name)
    keyboard.send_keys('^v')
    time.sleep(0.05)
    keyboard.send_keys('{ENTER}')
    # 优化：减少等待时间从 0.8-1.2s 到 0.5-0.7s
    time.sleep(random.uniform(0.5, 0.7))


def send_single_message(message: str):
    """发送单条消息（支持换行）"""
    lines = message.split('\n')
    for i, line in enumerate(lines):
        if line.strip():
            _copy_text(line)
            time.sleep(0.1)
            pyautogui.keyDown('ctrl')
            pyautogui.keyDown('v')
            pyautogui.keyUp('v')
            pyautogui.keyUp('ctrl')
            time.sleep(0.2)

        if i < len(lines) - 1:
            pyautogui.keyDown('shift')
            pyautogui.keyDown('return')
            pyautogui.keyUp('return')
            pyautogui.keyUp('shift')
            time.sleep(0.2)

    pyautogui.keyDown('return')
    pyautogui.keyUp('return')
    time.sleep(0.3)


def send_text(contact_name: str, message: str, stay_in_chat: bool = False) -> bool:
    """发送文字消息给指定联系人"""
    global _current_chat_contact

    print(f"发送消息给 {contact_name}...")

    if _current_chat_contact != contact_name:
        ensure_wechat_focused()
        search_contact(contact_name)
        _current_chat_contact = contact_name
    else:
        ensure_wechat_focused()

    pyautogui.click(*INPUT_BOX)
    time.sleep(0.3)
    send_single_message(message)

    print(f"[OK] 已发送给 {contact_name}")

    if not stay_in_chat:
        _current_chat_contact = None
    return True


def send_text_segments(contact_name: str, messages: list[str],
                       use_image_threshold: int = 5) -> bool:
    """智能分段发送多条消息"""
    if len(messages) > use_image_threshold:
        print(f"  消息较多({len(messages)}条)，生成图片发送...")
        try:
            from image_generator import create_message_image
            image_path = create_message_image(title="", content_lines=messages, footer="")
            return send_image(contact_name, image_path)
        except ImportError:
            print("  [警告] image_generator 不可用，逐条发送")

    ensure_wechat_focused()
    search_contact(contact_name)
    pyautogui.click(*INPUT_BOX)
    time.sleep(0.3)

    for msg in messages:
        if msg.strip():
            send_single_message(msg)
        else:
            keyboard.send_keys('{ENTER}')
            time.sleep(0.3)

    return True


def _copy_image_to_clipboard(image_path: str) -> bool:
    """将图片复制到剪贴板（CF_DIB格式）"""
    try:
        import win32clipboard
        image = Image.open(image_path)
        output = io.BytesIO()
        image.convert('RGB').save(output, 'BMP')
        data = output.getvalue()[14:]
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        print(f"复制图片到剪贴板失败: {e}")
        return False


def send_image(contact_name: str, image_path: str, message: str = "") -> bool:
    """发送图片给指定联系人"""
    global _current_chat_contact

    if not os.path.exists(image_path):
        print(f"[错误] 图片不存在: {image_path}")
        return False

    print(f"发送图片给 {contact_name}: {os.path.basename(image_path)}")

    if _current_chat_contact != contact_name:
        ensure_wechat_focused()
        search_contact(contact_name)
        _current_chat_contact = contact_name
    else:
        ensure_wechat_focused()

    if not _copy_image_to_clipboard(image_path):
        return False

    pyautogui.click(*INPUT_BOX)
    time.sleep(0.3)
    keyboard.send_keys('^v')
    time.sleep(0.5)

    if message:
        time.sleep(0.3)
        _copy_text(message)
        keyboard.send_keys('^v')
        time.sleep(0.3)

    time.sleep(0.5)
    keyboard.send_keys('{ENTER}')

    print(f"[OK] 图片已发送给 {contact_name}")
    return True


def _copy_file_to_clipboard(file_path: str) -> bool:
    """将文件复制到剪贴板（CF_HDROP格式）"""
    try:
        import win32clipboard
        import win32con

        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return False

        offset = 20
        file_list = file_path + '\x00\x00'
        file_bytes = file_list.encode('utf-16-le')

        dropfiles = struct.pack('<I', offset)
        dropfiles += struct.pack('<ii', 0, 0)
        dropfiles += struct.pack('<I', 0)
        dropfiles += struct.pack('<I', 1)  # fWide = True

        data = dropfiles + file_bytes

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        print(f"复制文件到剪贴板失败: {e}")
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return False


def _ctrl(key):
    """使用pyautogui发送Ctrl+Key（更可靠）"""
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown(key)
    pyautogui.keyUp(key)
    pyautogui.keyUp('ctrl')


def send_file(contact_name: str, file_path: str, message: str = "",
              stay_in_chat: bool = False) -> bool:
    """发送文件给指定联系人 - 使用AI助手相同的实现"""
    global _current_chat_contact

    if not os.path.exists(file_path):
        print(f"[错误] 文件不存在: {file_path}")
        return False

    print(f"发送文件给 {contact_name}: {os.path.basename(file_path)}")

    # 如果需要切换联系人，才需要激活和搜索
    if _current_chat_contact != contact_name:
        ensure_wechat_focused()
        search_contact(contact_name)
        _current_chat_contact = contact_name
    else:
        # 即使是同一个联系人，也要确保窗口有焦点
        ensure_wechat_focused()

    # 使用CF_HDROP格式复制文件到剪贴板
    if not _copy_file_to_clipboard(file_path):
        print("[错误] 无法复制文件到剪贴板")
        return False

    time.sleep(0.5)

    # 粘贴到聊天窗口
    pyautogui.click(*INPUT_BOX)
    time.sleep(0.3)
    _ctrl('v')
    time.sleep(1.5)  # 文件粘贴需要更长时间（与AI助手一致）

    # 添加文字说明（可选）
    if message:
        time.sleep(0.3)
        pyperclip.copy(message)
        _ctrl('v')
        time.sleep(0.3)

    # 发送
    time.sleep(0.5)
    pyautogui.press('enter')

    print(f"[OK] 文件已发送给 {contact_name}")

    # 如果不保持聊天状态，重置当前联系人
    if not stay_in_chat:
        _current_chat_contact = None

    return True


# ═══════════════════════════════════════════════════════
# 线程安全发送（API 服务器用）
# ═══════════════════════════════════════════════════════

_send_lock = threading.Lock()


def send_text_safe(contact_name: str, message: str, timeout: int = 30) -> dict:
    """线程安全的文字发送，返回结果字典"""
    with _send_lock:
        result = {"success": False, "error": None}
        try:
            def _do():
                try:
                    send_text(contact_name, message, stay_in_chat=True)
                    result["success"] = True
                except Exception as e:
                    result["error"] = str(e)

            t = threading.Thread(target=_do, daemon=True)
            t.start()
            t.join(timeout=timeout)

            if t.is_alive():
                result["error"] = f"发送超时({timeout}s)"
                _current_chat_contact = None
        except Exception as e:
            result["error"] = str(e)
    return result


def send_image_safe(contact_name: str, image_path: str, timeout: int = 45) -> dict:
    """线程安全的图片发送，返回结果字典"""
    with _send_lock:
        result = {"success": False, "error": None}
        try:
            def _do():
                try:
                    send_image(contact_name, image_path)
                    result["success"] = True
                except Exception as e:
                    result["error"] = str(e)

            t = threading.Thread(target=_do, daemon=True)
            t.start()
            t.join(timeout=timeout)

            if t.is_alive():
                result["error"] = f"发送超时({timeout}s)"
                _current_chat_contact = None
        except Exception as e:
            result["error"] = str(e)
    return result


def send_file_safe(contact_name: str, file_path: str, timeout: int = 45) -> dict:
    """线程安全的文件发送，返回结果字典"""
    with _send_lock:
        result = {"success": False, "error": None}
        try:
            def _do():
                try:
                    send_file(contact_name, file_path)
                    result["success"] = True
                except Exception as e:
                    result["error"] = str(e)

            t = threading.Thread(target=_do, daemon=True)
            t.start()
            t.join(timeout=timeout)

            if t.is_alive():
                result["error"] = f"发送超时({timeout}s)"
                _current_chat_contact = None
        except Exception as e:
            result["error"] = str(e)
    return result


# 兼容旧接口
send = send_text
