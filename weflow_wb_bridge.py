#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeFlow -> WorkBuddy Bridge (Python + pyautogui)
Same tech stack as wechat_sender

Features:
1. Subscribe WeFlow SSE, receive WeChat messages
2. Use pyautogui to activate WorkBuddy window
3. Click input box, paste message, send
"""

import os
import sys
import json
import time
import threading
import requests
from datetime import datetime
from typing import Optional, Dict, Any

# Fix encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sender'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))

import pyautogui
import pyperclip
from pywinauto import keyboard

# Config
WEFLOW_SSE_URL = "http://127.0.0.1:5031/api/v1/push/messages?access_token=eaf98e9bc0c13ea0c8e7cf0b29586669"
WEFLOW_API_BASE = "http://127.0.0.1:5031"

# WorkBuddy input box position (relative to window)
INPUT_X_RATIO = 0.625
INPUT_Y_OFFSET_FROM_BOTTOM = 232

# Dedup cache
_processed_keys: Dict[str, float] = {}
MAX_CACHE = 5000
CACHE_TIMEOUT = 300  # 5 minutes


# 统一日志函数 - 使用 core.config.log
try:
    from core.config import log as _config_log
    def log(message: str, tag: str = "WBBridge"):
        _config_log(message, tag)
except ImportError:
    # 兜底日志函数
    def log(message: str, tag: str = "WBBridge"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{tag}] {message}", flush=True)


# 导入语音转文字功能（本地 sherpa-onnx 模型）
_transcribe_voice_func = None

def _init_voice_model():
    """初始化本地语音模型"""
    global _transcribe_voice_func
    if _transcribe_voice_func is not None:
        return True
    try:
        from app import transcribe_voice
        _transcribe_voice_func = transcribe_voice
        log("[VOICE] Local sherpa-onnx model loaded")
        return True
    except ImportError as e:
        log(f"[VOICE] Local voice model not available: {e}")
        return False

def is_duplicate(key: str) -> bool:
    """Check if message is duplicate"""
    global _processed_keys
    
    # Clean expired cache
    current_time = time.time()
    expired = [k for k, v in _processed_keys.items() if current_time - v > CACHE_TIMEOUT]
    for k in expired:
        del _processed_keys[k]
    
    if len(_processed_keys) > MAX_CACHE:
        _processed_keys.clear()
    
    if key in _processed_keys:
        return True
    
    _processed_keys[key] = current_time
    return False


def get_workbuddy_window() -> Optional[Any]:
    """Get WorkBuddy window handle"""
    try:
        import win32gui
        import win32process
        import psutil
        
        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if 'workbuddy' in title.lower() or 'work buddy' in title.lower():
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        process = psutil.Process(pid)
                        if 'workbuddy' in process.name().lower():
                            extra.append(hwnd)
                    except:
                        pass
            return True
        
        handles = []
        win32gui.EnumWindows(callback, handles)
        return handles[0] if handles else None
    except Exception as e:
        log(f"[ERROR] Get WorkBuddy window failed: {e}")
        return None


def activate_workbuddy() -> bool:
    """Activate WorkBuddy window to foreground"""
    try:
        import win32gui
        import win32con
        import ctypes
        
        hwnd = get_workbuddy_window()
        if not hwnd:
            log("[ERROR] WorkBuddy not running")
            return False
        
        # Restore if minimized
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
        
        # Set foreground window
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        
        return True
    except Exception as e:
        log(f"[ERROR] Activate WorkBuddy failed: {e}")
        return False


def get_input_box_position() -> Optional[tuple]:
    """Get WorkBuddy input box coordinates"""
    try:
        import win32gui
        
        hwnd = get_workbuddy_window()
        if not hwnd:
            return None
        
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        x = rect[0] + int(width * INPUT_X_RATIO)
        y = rect[3] - INPUT_Y_OFFSET_FROM_BOTTOM
        
        return (x, y)
    except Exception as e:
        log(f"[ERROR] Get input box position failed: {e}")
        return None


def click_input_box() -> bool:
    """Click WorkBuddy input box"""
    try:
        pos = get_input_box_position()
        if not pos:
            return False
        
        pyautogui.moveTo(pos[0], pos[1], duration=0.2)
        time.sleep(0.1)
        pyautogui.click()
        time.sleep(0.3)
        
        return True
    except Exception as e:
        log(f"[ERROR] Click input box failed: {e}")
        return False


def send_text_to_workbuddy(text: str, stay_in_chat: bool = False) -> bool:
    """Send text to WorkBuddy (using pyautogui, same as wechat_sender)"""
    try:
        log(f"[SEND] Preparing to send: {text[:50]}...")
        
        # 1. Activate window
        if not activate_workbuddy():
            log("[ERROR] Activate WorkBuddy failed")
            return False
        
        # 2. Click input box
        if not click_input_box():
            log("[ERROR] Click input box failed")
            return False
        
        # 3. Copy to clipboard
        log("[SEND] Setting clipboard...")
        pyperclip.copy(text)
        time.sleep(0.3)
        
        # 4. Paste (using pyautogui, same as wechat_sender)
        log("[SEND] Pasting...")
        pyautogui.keyDown('ctrl')
        pyautogui.keyDown('v')
        pyautogui.keyUp('v')
        pyautogui.keyUp('ctrl')
        time.sleep(0.5)
        
        # 5. Send (unless stay_in_chat is True)
        if not stay_in_chat:
            log("[SEND] Pressing Enter to send...")
            pyautogui.press('enter')
            time.sleep(0.3)
            # Double press enter to ensure message is sent
            pyautogui.press('enter')
            time.sleep(0.2)
        
        log("[SEND] Success")
        return True
        
    except Exception as e:
        log(f"[ERROR] Send failed: {e}")
        return False


def _copy_image_to_clipboard(image_path: str) -> bool:
    """Copy image file to clipboard as DIB format"""
    try:
        from PIL import Image
        import io
        import win32clipboard
        import win32con
        
        image = Image.open(image_path)
        output = io.BytesIO()
        image.convert('RGB').save(output, 'BMP')
        data = output.getvalue()[14:]  # Remove BMP header
        output.close()
        
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        log(f"[ERROR] Copy image to clipboard failed: {e}")
        try:
            win32clipboard.CloseClipboard()
        except:
            pass
        return False


def send_text_and_image_to_workbuddy(text: str, image_path: str) -> bool:
    """Send text and image in one message to WorkBuddy"""
    try:
        log(f"[SEND] Preparing to send text + image: {text[:50]}...")
        
        # 1. Activate window
        if not activate_workbuddy():
            log("[ERROR] Activate WorkBuddy failed")
            return False
        
        # 2. Click input box
        if not click_input_box():
            log("[ERROR] Click input box failed")
            return False
        
        # 3. Copy and paste text
        log("[SEND] Setting text clipboard...")
        pyperclip.copy(text)
        time.sleep(0.3)
        
        log("[SEND] Pasting text...")
        pyautogui.keyDown('ctrl')
        pyautogui.keyDown('v')
        pyautogui.keyUp('v')
        pyautogui.keyUp('ctrl')
        time.sleep(0.5)
        
        # 4. Copy and paste image
        log("[SEND] Setting image clipboard...")
        if not _copy_image_to_clipboard(image_path):
            log("[ERROR] Copy image to clipboard failed")
            return False
        time.sleep(0.5)
        
        log("[SEND] Pasting image...")
        pyautogui.keyDown('ctrl')
        pyautogui.keyDown('v')
        pyautogui.keyUp('v')
        pyautogui.keyUp('ctrl')
        time.sleep(1.5)
        
        # 5. Send - try multiple methods
        log("[SEND] Pressing Enter to send...")
        pyautogui.press('enter')
        time.sleep(0.5)
        
        # Try again if needed (some apps need double enter)
        pyautogui.press('enter')
        time.sleep(0.3)
        
        log("[SEND] Success")
        return True
        
    except Exception as e:
        log(f"[ERROR] Send failed: {e}")
        return False


# Message type constants (same as WeFlow)
MSG_TYPE_TEXT = 1
MSG_TYPE_IMAGE = 3
MSG_TYPE_VOICE = 34
MSG_TYPE_VIDEO = 43
MSG_TYPE_EMOJI = 47
MSG_TYPE_CARD = 42
MSG_TYPE_LOCATION = 48
MSG_TYPE_LINK = 49


def get_message_type(msg: dict) -> str:
    """Get message type from localType or content"""
    local_type = msg.get('localType')
    content = msg.get('content', '')
    media_type = msg.get('mediaType')
    
    # Check localType first
    if local_type == MSG_TYPE_IMAGE:
        return 'image'
    elif local_type == MSG_TYPE_VOICE:
        return 'voice'
    elif local_type == MSG_TYPE_VIDEO:
        return 'video'
    elif local_type == MSG_TYPE_EMOJI:
        return 'emoji'
    elif local_type == MSG_TYPE_CARD:
        return 'card'
    elif local_type == MSG_TYPE_LOCATION:
        return 'location'
    elif local_type == MSG_TYPE_LINK:
        return 'link'
    
    # Check content keywords
    if '[图片]' in content or '[image]' in content.lower():
        return 'image'
    elif '[语音]' in content or '[voice]' in content.lower():
        return 'voice'
    elif '[视频]' in content or '[video]' in content.lower():
        return 'video'
    elif '[表情]' in content or '[emoji]' in content.lower():
        return 'emoji'
    elif '[名片]' in content or '[card]' in content.lower():
        return 'card'
    elif '[位置]' in content or '[location]' in content.lower():
        return 'location'
    elif '[链接]' in content or '[link]' in content.lower():
        return 'link'
    
    # Check mediaType
    if media_type in ['image', 3]:
        return 'image'
    elif media_type in ['voice', 34]:
        return 'voice'
    elif media_type in ['video', 43]:
        return 'video'
    
    # Check if has media URL
    if msg.get('mediaUrl') or msg.get('mediaLocalPath'):
        return 'media'
    
    return 'text'


def is_image_message(msg: dict) -> bool:
    """Check if message is image (for backward compatibility)"""
    return get_message_type(msg) == 'image'


def enrich_message_media(msg: dict) -> bool:
    """
    Enrich message with multimedia fields via API.
    SSE push doesn't include mediaUrl/mediaLocalPath, need to get from API.
    Same as AI assistant implementation.
    
    Returns:
        True if enrichment successful
    """
    try:
        session_id = msg.get('sessionId', '')
        content = msg.get('content', '')
        local_type = msg.get('localType')
        
        # Call API to get recent messages with media info
        url = f"{WEFLOW_API_BASE}/api/v1/messages"
        params = {
            "talker": session_id,
            "limit": 10,
            "media": "1",  # Include media info
            "access_token": "eaf98e9bc0c13ea0c8e7cf0b29586669"
        }
        
        log(f"[ENRICH] Getting media info from API for {session_id}")
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("messages", [])
        
        # Method 1: Match by content
        for m in messages:
            if m.get("content") == content:
                msg['mediaUrl'] = m.get('mediaUrl', '')
                msg['mediaLocalPath'] = m.get('mediaLocalPath', '')
                msg['mediaType'] = m.get('mediaType', '')
                log(f"[ENRICH] Matched by content, mediaUrl={msg.get('mediaUrl', '')[:50]}...")
                return True
        
        # Method 2: Match by localType for images
        if local_type == 3 or '[图片]' in content:
            for m in messages:
                if m.get("localType") == 3:
                    msg['mediaUrl'] = m.get('mediaUrl', '')
                    msg['mediaLocalPath'] = m.get('mediaLocalPath', '')
                    msg['mediaType'] = m.get('mediaType', '')
                    log(f"[ENRICH] Matched image by localType")
                    return True
        
        # Method 3: Match by localType for voice
        elif local_type == 34 or '[语音]' in content:
            for m in messages:
                if m.get("localType") == 34:
                    msg['mediaUrl'] = m.get('mediaUrl', '')
                    msg['mediaLocalPath'] = m.get('mediaLocalPath', '')
                    msg['mediaType'] = m.get('mediaType', '')
                    log(f"[ENRICH] Matched voice by localType")
                    return True
        
        # Method 4: Match by localType for video
        elif local_type == 43 or '[视频]' in content:
            for m in messages:
                if m.get("localType") == 43:
                    msg['mediaUrl'] = m.get('mediaUrl', '')
                    msg['mediaLocalPath'] = m.get('mediaLocalPath', '')
                    msg['mediaType'] = m.get('mediaType', '')
                    log(f"[ENRICH] Matched video by localType")
                    return True
        
        # Method 5: Match by localType
        if local_type:
            for m in messages:
                if m.get("localType") == local_type:
                    msg['mediaUrl'] = m.get('mediaUrl', '')
                    msg['mediaLocalPath'] = m.get('mediaLocalPath', '')
                    msg['mediaType'] = m.get('mediaType', '')
                    log(f"[ENRICH] Matched by localType={local_type}")
                    return True
        
        # Method 6: Use most recent multimedia message
        for m in messages:
            if m.get("localType") in (3, 34, 43, 47):
                msg['mediaUrl'] = m.get('mediaUrl', '')
                msg['mediaLocalPath'] = m.get('mediaLocalPath', '')
                msg['mediaType'] = m.get('mediaType', '')
                log(f"[ENRICH] Using recent multimedia message")
                return True
        
        log("[ENRICH] Failed to match any media")
        return False
        
    except Exception as e:
        log(f"[ENRICH] Error: {e}")
        return False


def get_image_path_from_message(msg: dict) -> Optional[str]:
    """Get image path from message - use local path if available, otherwise download"""
    # First try to use local path from WeFlow
    local_path = msg.get('mediaLocalPath', '')
    if local_path and os.path.exists(local_path):
        log(f"[IMAGE] Using local file: {local_path}")
        return local_path
    
    # Fallback to download from WeFlow using mediaUrl
    downloaded_path = download_image_from_message(msg)
    if downloaded_path:
        return downloaded_path
    
    # Last resort: try to find in cache by session and time
    return find_latest_image_in_cache(msg.get('sessionId', ''))


def download_image_from_message(msg: dict) -> Optional[str]:
    """Download image from WeFlow using mediaUrl"""
    try:
        # Use mediaUrl from message (most accurate)
        media_url = msg.get('mediaUrl', '')
        if not media_url:
            # Fallback: try to construct from messageKey
            message_key = msg.get('messageKey', '')
            if message_key:
                from urllib.parse import quote
                encoded_key = quote(message_key, safe='')
                media_url = f"{WEFLOW_API_BASE}/api/v1/message/media?messageKey={encoded_key}&access_token=eaf98e9bc0c13ea0c8e7cf0b29586669"
            else:
                return None
        
        log(f"[IMAGE] Downloading: {media_url}")
        
        import tempfile
        temp_file = tempfile.mktemp(suffix='.jpg')
        
        response = requests.get(media_url, timeout=30)
        if response.status_code == 200:
            with open(temp_file, 'wb') as f:
                f.write(response.content)
            log(f"[IMAGE] Saved: {temp_file}")
            return temp_file
    except Exception as e:
        log(f"[ERROR] Download image failed: {e}")
    return None


def get_media_download_url(msg: dict) -> str:
    """Get media download URL for CLAW - use mediaUrl from message if available"""
    # First try to use mediaUrl from message (most accurate)
    media_url = msg.get('mediaUrl', '')
    if media_url:
        return media_url
    
    # Fallback: construct URL from messageKey (may not work for all media types)
    msg_key = msg.get('messageKey', '')
    if msg_key:
        from urllib.parse import quote
        encoded_key = quote(msg_key, safe='')
        return f"{WEFLOW_API_BASE}/api/v1/message/media?messageKey={encoded_key}&access_token=eaf98e9bc0c13ea0c8e7cf0b29586669"
    
    return ""


def find_latest_image_in_cache(session_id: str) -> Optional[str]:
    """Find the latest image file in WeFlow cache for a session"""
    try:
        cache_dir = os.path.expanduser(r'~\AppData\Roaming\weflow\cache\api-media')
        
        # Look for session directory
        if session_id:
            session_dir = os.path.join(cache_dir, session_id, 'images')
            if os.path.exists(session_dir):
                files = [(f, os.path.getmtime(os.path.join(session_dir, f))) 
                        for f in os.listdir(session_dir) 
                        if f.endswith(('.jpg', '.png', '.jpeg'))]
                if files:
                    files.sort(key=lambda x: x[1], reverse=True)
                    latest = os.path.join(session_dir, files[0][0])
                    log(f"[IMAGE] Found in cache: {latest}")
                    return latest
        
        # Search all sessions for recent images (last 60 seconds)
        import time
        current_time = time.time()
        recent_files = []
        
        for root, dirs, files in os.walk(cache_dir):
            if 'images' in root:
                for f in files:
                    if f.endswith(('.jpg', '.png', '.jpeg')):
                        path = os.path.join(root, f)
                        mtime = os.path.getmtime(path)
                        if current_time - mtime < 60:  # Last 60 seconds
                            recent_files.append((path, mtime))
        
        if recent_files:
            recent_files.sort(key=lambda x: x[1], reverse=True)
            log(f"[IMAGE] Found recent in cache: {recent_files[0][0]}")
            return recent_files[0][0]
            
    except Exception as e:
        log(f"[ERROR] Find image in cache failed: {e}")
    return None


def send_image_to_workbuddy(image_path: str) -> bool:
    """Send image to WorkBuddy"""
    try:
        from PIL import Image
        import io
        import win32clipboard
        import win32con
        
        log(f"[IMAGE] Sending image: {image_path}")
        
        # Activate window
        if not activate_workbuddy():
            return False
        
        if not click_input_box():
            return False
        
        # Copy image to clipboard
        image = Image.open(image_path)
        output = io.BytesIO()
        image.convert('RGB').save(output, 'BMP')
        data = output.getvalue()[14:]  # Remove BMP header
        output.close()
        
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        
        # Paste
        time.sleep(0.5)
        pyautogui.keyDown('ctrl')
        pyautogui.keyDown('v')
        pyautogui.keyUp('v')
        pyautogui.keyUp('ctrl')
        time.sleep(1.0)
        
        # Send
        pyautogui.press('enter')
        time.sleep(0.3)
        
        log("[IMAGE] Send success")
        return True
        
    except Exception as e:
        log(f"[ERROR] Send image failed: {e}")
        return False


def is_at_me(content: str) -> bool:
    """Check if message is @ me (Waterspinach/CLAW/李生/畅腾升降桌)"""
    at_keywords = ['@Waterspinach', '@CLAW', '@李生', '@畅腾', '@升降桌', '@智能升降桌']
    content_upper = content.upper()
    for keyword in at_keywords:
        if keyword.upper() in content_upper:
            return True
    # Check for @ followed by bot name patterns
    if '@' in content:
        # Common bot name patterns
        bot_patterns = ['Waterspinach', '李生', '畅腾', '升降桌', '智能', 'CLAW']
        for pattern in bot_patterns:
            if f'@{pattern}' in content or f'@{pattern.upper()}' in content_upper:
                return True
    return False


def extract_question_from_at(content: str) -> str:
    """Extract actual question from @ message"""
    # Remove @mentions
    import re
    # Remove @xxx patterns
    cleaned = re.sub(r'@[^\s@]+', '', content)
    # Remove extra spaces
    cleaned = ' '.join(cleaned.split())
    return cleaned.strip()


def handle_message(msg: dict):
    """Handle received message - send to WorkBuddy"""
    try:
        source = msg.get('sourceName', '')
        content = msg.get('content', '')
        msg_key = msg.get('messageKey', '')
        session_id = msg.get('sessionId', '')
        group_name = msg.get('groupName', '')
        media_local_path = msg.get('mediaLocalPath', '')
        media_url = msg.get('mediaUrl', '')
        create_time = msg.get('createTime', '')
        source_id = msg.get('sourceId', '')  # 发送者ID
        
        # Filter out official accounts and service accounts
        # Official accounts usually have IDs starting with 'gh_' or contain specific keywords
        if source_id and source_id.startswith('gh_'):
            log(f"[SKIP] Official account message: {source} (ID: {source_id})")
            return
        
        # Also filter by common official account name patterns
        official_keywords = ['公众号', '服务号', '订阅号', '小程序', '视频号']
        if any(keyword in source for keyword in official_keywords):
            log(f"[SKIP] Official/service account message: {source}")
            return
        
        # Handle group messages with @
        if group_name:
            # Check if @ me
            if not is_at_me(content):
                log(f"[SKIP] Group message not @ me: {source} @ {group_name}")
                return
            log(f"[AT] Group message @ me from {source} @ {group_name}")
            # Extract actual question
            question = extract_question_from_at(content)
            msg['_is_at_message'] = True
            msg['_at_question'] = question
            msg['_at_sender'] = source
            msg['_group_name'] = group_name
        
        # Enhanced dedup: use combination key (messageKey may be empty or unreliable)
        dup_key = f"{msg_key}|{source}|{content}|{create_time}"
        if is_duplicate(dup_key):
            log(f"[DEDUP] Skip duplicate message from: {source}")
            return
        
        log(f"[KEY] dup_key={dup_key[:100]}")
        
        display_name = source
        log(f"[MSG] {display_name} : {content}")
        
        # Get message type
        msg_type = get_message_type(msg)
        log(f"[DEBUG] Message type: {msg_type}")
        
        # Enrich multimedia fields via API if needed
        # SSE push doesn't include mediaUrl/mediaLocalPath
        if msg_type in ('image', 'voice', 'video', 'emoji', 'media') and not media_url and not media_local_path:
            log("[ENRICH] Multimedia fields missing, trying to get from API...")
            if enrich_message_media(msg):
                media_url = msg.get('mediaUrl', '')
                media_local_path = msg.get('mediaLocalPath', '')
                log(f"[ENRICH] Success! mediaUrl={media_url[:50] if media_url else 'None'}..., mediaLocalPath={media_local_path if media_local_path else 'None'}")
            else:
                log("[ENRICH] Failed to get media info from API")
        
        # Build download URL
        download_url = get_media_download_url(msg)
        
        if msg_type == 'image':
            log("[IMAGE] Processing image message...")
            # Get image path
            image_path = get_image_path_from_message(msg)
            log(f"[IMAGE] Got image path: {image_path}")

            # FIX: 只发送图片路径文本，不粘贴图片数据到WorkBuddy
            # 原因：图片base64数据会爆炸上下文，导致AI上下文被压缩
            # AI收到路径后，可通过API /api/image/match 分析图片
            if image_path and os.path.exists(image_path):
                text = f"[{display_name}]: [图片]\nPath: {image_path}"
                if download_url:
                    text += f"\nURL: {download_url}"
                log(f"[IMAGE] Sending image path text only (no image data) to WorkBuddy...")
                send_text_to_workbuddy(text)
                log("[IMAGE] Sent image path text successfully")
                # Clean temp file only if it was downloaded (not local cache)
                if image_path != media_local_path:
                    try:
                        os.remove(image_path)
                        log(f"[IMAGE] Cleaned up temp file: {image_path}")
                    except Exception as e:
                        log(f"[IMAGE] Failed to cleanup temp file: {e}")
            else:
                # Fallback: send text only if image cannot be loaded
                log(f"[IMAGE] Image path not available, sending text only")
                text = f"[{display_name}]: [图片 - 加载失败]\nURL: {download_url}"
                send_text_to_workbuddy(text)
                
        elif msg_type == 'voice':
            log("[VOICE] Processing voice message...")
            
            # 语音转文字（使用本地 sherpa-onnx 模型）
            transcribed_text = ""
            if media_local_path and os.path.exists(media_local_path):
                try:
                    log(f"[VOICE] Transcribing: {media_local_path}")
                    
                    # 初始化本地模型
                    if _init_voice_model():
                        # 使用本地模型转文字
                        transcribed_text = _transcribe_voice_func(media_local_path)
                        if transcribed_text and transcribed_text != "[语音识别失败]":
                            log(f"[VOICE→TEXT] {transcribed_text[:50]}...")
                        else:
                            log(f"[VOICE] Transcribed text is empty or failed")
                    else:
                        # 本地模型不可用，使用 API 作为备选
                        log("[VOICE] Using API fallback...")
                        url = "http://127.0.0.1:5032/api/voice/transcribe"
                        with open(media_local_path, 'rb') as f:
                            files = {'voice': f}
                            resp = requests.post(url, files=files, timeout=30)
                        if resp.status_code == 200:
                            result = resp.json()
                            transcribed_text = result.get('text', '')
                            if transcribed_text:
                                log(f"[VOICE→TEXT] {transcribed_text[:50]}...")
                except Exception as e:
                    log(f"[VOICE] Transcribe failed: {e}")
            else:
                log(f"[VOICE] No local path or file not exists: {media_local_path}")
            
            # 发送给 WorkBuddy
            if transcribed_text:
                # 转文字成功，只发送文字内容
                text = f"[{display_name}]: {transcribed_text}"
            else:
                # 转文字失败，发送语音标记和路径
                text = f"[{display_name}]: [Voice message]"
                if media_local_path:
                    text += f"\nPath: {media_local_path}"
            send_text_to_workbuddy(text)
            
        elif msg_type == 'video':
            log("[VIDEO] Processing video message...")
            text = f"[VIDEO from {display_name}]\nURL: {download_url}"
            if media_local_path:
                text += f"\nPath: {media_local_path}"
            send_text_to_workbuddy(text)
            
        elif msg_type == 'emoji':
            log("[EMOJI] Processing emoji message...")
            text = f"[EMOJI from {display_name}]\nURL: {download_url}"
            if media_local_path:
                text += f"\nPath: {media_local_path}"
            send_text_to_workbuddy(text)
            
        elif msg_type == 'card':
            log("[CARD] Processing card message...")
            text = f"[CARD from {display_name}]\nURL: {download_url}"
            send_text_to_workbuddy(text)
            
        elif msg_type == 'location':
            log("[LOCATION] Processing location message...")
            text = f"[LOCATION from {display_name}]\nURL: {download_url}"
            send_text_to_workbuddy(text)
            
        elif msg_type == 'link':
            log("[LINK] Processing link message...")
            # For links: use the actual URL if available
            link_url = media_url or content
            text = f"[LINK from {display_name}]\nURL: {link_url}"
            send_text_to_workbuddy(text)
            
        elif msg_type == 'media':
            log("[MEDIA] Processing other media message...")
            text = f"[MEDIA from {display_name}]\nURL: {download_url}"
            if media_local_path:
                text += f"\nPath: {media_local_path}"
            send_text_to_workbuddy(text)
            
        else:
            # Text message
            # FALLBACK: 如果文本内容是[图片]但类型识别失败，仍然获取图片路径发送
            if '[图片]' in content and not msg.get('_is_at_message'):
                log("[IMAGE-FALLBACK] Content has [图片] but type was not image, getting image path...")
                image_path = get_image_path_from_message(msg)
                if image_path and os.path.exists(image_path):
                    text = f"[{display_name}]: [图片]\nPath: {image_path}"
                    if download_url:
                        text += f"\nURL: {download_url}"
                    log(f"[IMAGE-FALLBACK] Sending image path: {image_path}")
                    send_text_to_workbuddy(text)
                    # Clean temp file
                    if image_path != media_local_path:
                        try:
                            os.remove(image_path)
                        except:
                            pass
                else:
                    text = f"[{display_name}] {content}"
                    if download_url:
                        text += f"\nURL: {download_url}"
                    send_text_to_workbuddy(text)
            elif msg.get('_is_at_message'):
                question = msg.get('_at_question', content)
                sender = msg.get('_at_sender', display_name)
                group = msg.get('_group_name', '')
                text = f"[GROUP@{group}] [{sender}]: {question}"
                send_text_to_workbuddy(text)
            else:
                text = f"[{display_name}] {content}"
                send_text_to_workbuddy(text)
            
    except Exception as e:
        log(f"[ERROR] Handle message failed: {e}")


def connect_sse():
    """Connect WeFlow SSE and process messages"""
    log("[CONNECT] Connecting to WeFlow SSE...")
    
    while True:
        try:
            response = requests.get(
                WEFLOW_SSE_URL,
                stream=True,
                timeout=(10, None),
                headers={'Accept': 'text/event-stream'}
            )
            response.raise_for_status()
            
            log("[OK] SSE connected, waiting for messages...")
            
            buffer = ""
            current_event = ""
            
            for line in response.iter_lines(decode_unicode=True):
                if line is None:
                    continue
                
                line_str = line if isinstance(line, str) else line.decode('utf-8')
                
                if line_str == "":
                    # Empty line means event end
                    if current_event and buffer:
                        if current_event == "message.new":
                            try:
                                msg = json.loads(buffer)
                                handle_message(msg)
                            except json.JSONDecodeError as e:
                                log(f"[ERROR] JSON parse failed: {e}")
                        elif current_event == "ready":
                            log("[OK] WeFlow handshake OK")
                    
                    buffer = ""
                    current_event = ""
                    continue
                
                if line_str.startswith("event:"):
                    current_event = line_str[6:].strip()
                elif line_str.startswith("data:"):
                    buffer = line_str[5:].strip()
                    
        except requests.exceptions.ReadTimeout:
            log("[RECONNECT] Read timeout, reconnecting...")
            time.sleep(1)
        except Exception as e:
            log(f"[ERROR] Connection failed: {e}, retry in 5s...")
            time.sleep(5)


def main():
    """Main function"""
    # 简洁的启动信息
    log("[OK] Bridge 启动完成")

    # Check if WorkBuddy is running
    if not get_workbuddy_window():
        log("[ERROR] WorkBuddy 未运行，请先启动 WorkBuddy")
        input("按 Enter 退出...")
        return

    log("[OK] WorkBuddy 已连接")

    # Connect SSE
    connect_sse()


if __name__ == "__main__":
    main()
