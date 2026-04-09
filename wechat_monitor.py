# -*- coding: utf-8 -*-
"""
微信实时监控 + WorkBuddy AI 自动回复
──────────────────────────────────────
流程：
  1. 截图左侧会话列表
  2. 检测红色未读角标 → PaddleOCR 识别联系人名
  3. 白名单过滤（桌面 微信联系人昵称.txt）
  4. 点开聊天窗口，截图识别最近消息
  5. 写入 wb_comm/pending.json，等待 workbuddy_reply.py 写回 reply.json
  6. 粘贴发送回复
"""

import os
import sys
import io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import re
import time
import ctypes
import ctypes.wintypes
import hashlib
import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pyautogui
import pyperclip
from PIL import Image
from pywinauto import keyboard

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# 抑制 paddle 的 DeprecationWarning 等噪音日志
warnings.filterwarnings('ignore')
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['GLOG_v'] = '0'
os.environ['GLOG_minloglevel'] = '3'

# =====================================================================
# ★ 配置区 — 根据需要修改
# =====================================================================

MONITOR_INTERVAL = 3.0        # 主循环间隔（秒）
CHAT_LOAD_WAIT   = 2.5        # 点击联系人后等聊天加载的时间（秒）
REPLY_TIMEOUT    = 90         # 等待 AI 回复的超时（秒）

# 会话列表区域（相对微信窗口宽度的比例）
# 需要包含头像+昵称+红点，右边界要足够宽
SESSION_LIST_LEFT_RATIO  = 0.0
SESSION_LIST_RIGHT_RATIO = 0.65

# 永远跳过的系统账号黑名单
SKIP_CONTACTS = {"文件传输助手", "微信团队", "腾讯新闻", "服务通知"}

# 白名单文件：每行一个昵称，只回复在里面的联系人
WHITELIST_FILE = Path.home() / "Desktop" / "微信联系人昵称.txt"

# 文件通信目录（与 workbuddy_reply.py 共享）
COMM_DIR      = Path(__file__).parent / "wb_comm"
PENDING_FILE  = COMM_DIR / "pending.json"
REPLY_FILE    = COMM_DIR / "reply.json"

# 日志文件
LOG_FILE = Path(__file__).parent / "wechat_monitor_log.txt"

# =====================================================================


# ─────────────────── 日志 ────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ─────────────────── 微信窗口 ────────────────────────────────────────

def find_wechat_window():
    """找微信窗口，返回 (hwnd, {x,y,w,h}) 或 (None, None)"""
    hwnd = 0
    for title in ["微信", "WeChat"]:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            break
    if not hwnd:
        return None, None

    # 还原并激活
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.3)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win = dict(x=rect.left, y=rect.top,
               w=rect.right - rect.left,
               h=rect.bottom - rect.top)
    return hwnd, win


def activate_wechat(hwnd):
    """把微信窗口拉到前台"""
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


# ─────────────────── PaddleOCR 单例 ──────────────────────────────────

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        log("初始化 PaddleOCR（首次较慢）...")
        import paddleocr
        _ocr_engine = paddleocr.PaddleOCR(
            use_angle_cls=False,
            lang='ch',
            use_gpu=False,
            show_log=False,
        )
        log("PaddleOCR 就绪")
    return _ocr_engine


def ocr_image(pil_img: Image.Image) -> list:
    """
    识别图片，返回 [(text, x_center, y_center), ...]
    按 y_center 升序（从上到下）排列。
    """
    ocr = get_ocr_engine()
    arr = np.array(pil_img.convert("RGB"))
    result = ocr.ocr(arr, cls=False)
    items = []
    if not result or not result[0]:
        return items
    for item in result[0]:
        box, (text, conf) = item
        text = text.strip()
        if conf < 0.35 or not text:
            continue
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        xc = (min(xs) + max(xs)) / 2
        yc = (min(ys) + max(ys)) / 2
        items.append((text, float(xc), float(yc)))
    items.sort(key=lambda i: i[2])
    return items


# ─────────────────── 白名单 ──────────────────────────────────────────

_whitelist: set = None

def load_whitelist(force: bool = False) -> set:
    """加载桌面白名单，返回昵称集合。force=True 强制重新读取。"""
    global _whitelist
    if _whitelist is not None and not force:
        return _whitelist
    if not WHITELIST_FILE.exists():
        log(f"[白名单] 文件不存在 {WHITELIST_FILE}，将回复所有联系人")
        _whitelist = set()
        return _whitelist
    names = {l.strip() for l in WHITELIST_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}
    _whitelist = names
    log(f"[白名单] 已加载 {len(names)} 个联系人")
    return _whitelist


def in_whitelist(name: str) -> bool:
    """
    白名单命中判断（支持模糊匹配，应对OCR截断）。
    白名单为空时视为不限制，全部放行。
    """
    wl = load_whitelist()
    if not wl:
        return True
    if name in wl:
        return True
    for wname in wl:
        if name in wname or wname in name:
            return True
    return False


# ─────────────────── 会话列表 → 未读联系人 ───────────────────────────

def screenshot_session_list(win) -> Image.Image:
    """截取左侧会话列表区域（跳过顶部搜索栏）"""
    x = win['x'] + int(win['w'] * SESSION_LIST_LEFT_RATIO)
    y = win['y'] + int(win['h'] * 0.08)
    w = int(win['w'] * (SESSION_LIST_RIGHT_RATIO - SESSION_LIST_LEFT_RATIO))
    h = int(win['h'] * 0.85)
    return pyautogui.screenshot(region=(x, y, w, h))


def img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()


def _find_red_clusters(arr: np.ndarray) -> list:
    """
    在 RGB ndarray 中找红色未读角标，返回每个角标的 y 中心坐标列表。
    微信红点特征：红色背景 + 白色数字。
    检测逻辑：
      1. 找高纯度红色像素（R>230, G<110, B<110, R-G>130）
      2. 找白色像素（R>230, G>230, B>230）
      3. 对每个红色簇，检查其内部是否包含足够的白色像素（数字）
      4. 按行聚类，过滤噪点
    """
    r = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    b = arr[:, :, 2].astype(int)

    # 红色背景：高纯度红
    red_mask = (r > 230) & (g < 110) & (b < 110) & ((r - g) > 130) & ((r - b) > 130)

    # 白色数字：RGB 都接近 255
    white_mask = (r > 230) & (g > 230) & (b > 230)

    red_pixels = np.argwhere(red_mask)
    white_pixels = np.argwhere(white_mask)

    if len(red_pixels) == 0:
        return []

    # 将白色像素坐标转换为集合，便于快速查找
    white_pixel_set = set(map(tuple, white_pixels))

    # 按行聚类红色像素，间距 ≤ 8px 归为同一角标
    rows = sorted(set(red_pixels[:, 0].tolist()))
    clusters, cluster = [], [rows[0]]
    for row in rows[1:]:
        if row - cluster[-1] <= 8:
            cluster.append(row)
        else:
            clusters.append(cluster)
            cluster = [row]
    clusters.append(cluster)

    result = []
    for c in clusters:
        # 取该行范围内的所有红色像素
        c_set = set(c)
        c_pixels = red_pixels[[px[0] in c_set for px in red_pixels]]
        if len(c_pixels) < 5:   # 过滤零散噪点
            continue

        # 检查红色簇内是否有白色像素（数字）
        # 取红色像素的边界框
        row_min, row_max = int(np.min(c_pixels[:, 0])), int(np.max(c_pixels[:, 0]))
        col_min, col_max = int(np.min(c_pixels[:, 1])), int(np.max(c_pixels[:, 1]))

        # 在边界框内找白色像素
        white_in_red = sum(1 for (ry, rx) in white_pixels
                         if row_min <= ry <= row_max and col_min <= rx <= col_max)

        # 至少要有 3 个白色像素才算有效红点（数字）
        if white_in_red < 3:
            continue

        cy = int(np.mean(c_pixels[:, 0]))
        result.append(cy)

    return result


def detect_unread_contacts(session_img: Image.Image) -> list:
    """
    从会话列表截图中检测有未读消息的联系人名。
    策略：
      1. 找红色角标 → 确定每个未读行的 Y 坐标
      2. 针对每个红点，单独截取该行左侧一小条图像（联系人名所在区域）
      3. 对小图做 OCR，只取最左侧、最靠近红点的文字 = 联系人名
      4. 白名单 + 黑名单过滤
    """
    arr = np.array(session_img.convert("RGB"))
    red_y_list = _find_red_clusters(arr)
    if not red_y_list:
        return []

    img_w = session_img.width
    img_h = session_img.height

    # 联系人名噪音过滤 —— 只过滤明确的 UI 元素，保留空格和所有字符
    _noise_pats = [
        re.compile(r'^\d{1,2}:\d{2}$'),            # 纯时间 12:30
        re.compile(r'^[昨今明]天\s*\d'),            # 昨天 12:30
        re.compile(r'^星期[一二三四五六日]\s*\d'),   # 星期一 12:30
        re.compile(r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}'),  # 日期
        re.compile(r'^\d+$'),                       # 纯数字
        re.compile(r'^[\s]+$'),                     # 纯空白
        re.compile(r'分享的|的视频|的图片|的文件|的链接'),  # 消息预览
    ]
    def is_noise(t):
        # 空字符串直接过滤
        if not t or not t.strip():
            return True
        # 过长的文字是消息预览而非昵称
        if len(t) > 30:
            return True
        for p in _noise_pats:
            if p.search(t):
                return True
        return False

    contacts = []

    for uy in red_y_list:
        # 截取红点所在行的联系人名区域
        # 截图范围是窗口 0~65%，头像约占 0~9%，昵称在 9%~60%
        row_top    = max(0, uy - 20)
        row_bottom = min(img_h, uy + 20)
        name_left  = int(img_w * 0.09)   # 跳过头像
        name_right = int(img_w * 0.60)   # 昵称右边界（不含时间/预览）

        if row_bottom <= row_top or name_right <= name_left:
            continue

        row_img = session_img.crop((name_left, row_top, name_right, row_bottom))

        try:
            items = ocr_image(row_img)
        except Exception as e:
            log(f"[OCR] 行识别失败: {e}")
            continue

        if not items:
            continue

        # 按 X 从左到右，取第一个不是噪音的文字
        items.sort(key=lambda i: i[1])  # i[1] = xc
        name = None
        for text, xc, yc in items:
            if not is_noise(text):
                name = text
                break

        if not name:
            continue
        if name in SKIP_CONTACTS:
            continue
        if not in_whitelist(name):
            log(f"  [白名单] 跳过: {name}")
            continue
        if name not in contacts:
            contacts.append(name)

    return contacts


# ─────────────────── 打开聊天 ────────────────────────────────────────

def open_contact_chat(win, contact_name: str) -> bool:
    """
    始终用 Ctrl+F 搜索联系人昵称，截图 OCR 定位第一条搜索结果并点击进入聊天。
    流程：
      1. Ctrl+F 唤起搜索框
      2. 粘贴昵称
      3. 等待搜索结果渲染
      4. 截图搜索结果区域，OCR 找到匹配条目 → 点击
      5. 找不到则点击搜索框下方固定坐标（第一条结果默认位置）
    """
    log(f"  [搜索] Ctrl+F 搜索: {contact_name}")

    # 激活微信 + 发送 Ctrl+F
    keyboard.send_keys('^f')
    time.sleep(0.5)

    # 清空搜索框并输入昵称
    keyboard.send_keys('^a')
    time.sleep(0.1)
    pyperclip.copy(contact_name)
    keyboard.send_keys('^v')
    time.sleep(1.0)   # 等搜索结果加载

    # 截取搜索结果区域（微信搜索结果弹出在左侧面板，约占窗口左侧 35%）
    sx = win['x']
    sy = win['y'] + int(win['h'] * 0.10)
    sw = int(win['w'] * 0.35)
    sh = int(win['h'] * 0.80)
    search_img = pyautogui.screenshot(region=(sx, sy, sw, sh))

    # OCR 识别搜索结果，找与 contact_name 最相似的条目
    clicked = False
    try:
        items = ocr_image(search_img)
        for text, xc, yc in items:
            if contact_name in text or text in contact_name:
                abs_x = sx + int(xc)
                abs_y = sy + int(yc)
                log(f"  [搜索] 找到结果: '{text}' @ ({abs_x}, {abs_y})")
                pyautogui.click(abs_x, abs_y)
                clicked = True
                break
    except Exception as e:
        log(f"  [搜索] OCR识别失败: {e}")

    if not clicked:
        # 搜索结果第一条固定坐标兜底（搜索框下方约 15% 高度处，X 居中在左侧面板）
        fallback_x = win['x'] + int(win['w'] * 0.17)
        fallback_y = win['y'] + int(win['h'] * 0.25)
        log(f"  [搜索] OCR未找到，点击兜底坐标 ({fallback_x}, {fallback_y})")
        pyautogui.click(fallback_x, fallback_y)

    # 确保微信在前台，等聊天内容加载
    ctypes.windll.user32.ShowWindow(
        ctypes.windll.user32.FindWindowW(None, "微信") or
        ctypes.windll.user32.FindWindowW(None, "WeChat"), 9)
    time.sleep(CHAT_LOAD_WAIT)
    return True


# ─────────────────── 聊天内容提取 ────────────────────────────────────

def screenshot_chat_area(win) -> Image.Image:
    """截取右侧聊天气泡区域（尽量大，跳过标题栏和输入框）"""
    chat_left = int(win['w'] * 0.33)
    x = win['x'] + chat_left
    y = win['y'] + int(win['h'] * 0.08)   # 跳过标题栏
    w = win['w'] - chat_left - 5
    h = int(win['h'] * 0.75)              # 覆盖更多聊天气泡
    return pyautogui.screenshot(region=(x, y, w, h))


def extract_recent_messages(chat_img: Image.Image, n: int = 8) -> list:
    """
    从聊天截图 OCR 提取最近 n 条消息。
    返回 [{"speaker": "other"/"self", "text": "..."}, ...]

    判断 speaker 依据：气泡 X 中心位置
      - 左半部分 (<45%) → 对方
      - 右半部分 (>55%) → 自己
      - 中间区域         → 时间戳或系统消息，跳过
    """
    try:
        items = ocr_image(chat_img)
    except Exception as e:
        log(f"[OCR] 聊天区域识别失败: {e}")
        return []

    img_w = chat_img.width

    _ts_pats = [
        re.compile(r'^\d{1,2}:\d{2}$'),
        re.compile(r'^[昨今明]天'),
        re.compile(r'^星期[一二三四五六日]'),
        re.compile(r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}'),
    ]
    def is_ts(t):
        for p in _ts_pats:
            if p.match(t): return True
        return False

    msgs = []
    for text, xc, yc in items:   # 已按 y 排序
        if is_ts(text) or len(text) < 1:
            continue
        ratio = xc / img_w
        if ratio < 0.45:
            speaker = "other"
        elif ratio > 0.55:
            speaker = "self"
        else:
            continue   # 中间 → 系统消息/时间戳

        # 尝试合并相邻同 speaker 同 Y 的碎片文字（PaddleOCR 偶尔把一行拆成两块）
        if msgs and msgs[-1]["speaker"] == speaker and abs(yc - msgs[-1].get("_yc", 0)) < 12:
            msgs[-1]["text"] += text
        else:
            msgs.append({"speaker": speaker, "text": text, "_yc": yc})

    # 去掉内部 _yc 辅助字段
    for m in msgs:
        m.pop("_yc", None)

    return msgs[-n:] if len(msgs) > n else msgs


# ─────────────────── AI 回复通信 ─────────────────────────────────────

def request_reply(contact_name: str, messages: list) -> str:
    """
    把任务写入 pending.json，等待 workbuddy_reply.py 写回 reply.json。
    返回回复文本，超时返回 None。
    """
    COMM_DIR.mkdir(exist_ok=True)

    # 清理上一次的残留
    if REPLY_FILE.exists():
        REPLY_FILE.unlink()

    task = {
        "id":       datetime.now().strftime("%Y%m%d_%H%M%S"),
        "contact":  contact_name,
        "messages": messages,
        "time":     datetime.now().isoformat(),
        "status":   "pending",
    }
    PENDING_FILE.write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  [任务] 已写入，等待 WorkBuddy 回复（超时 {REPLY_TIMEOUT}s）...")

    deadline = time.time() + REPLY_TIMEOUT
    while time.time() < deadline:
        if REPLY_FILE.exists():
            try:
                data = json.loads(REPLY_FILE.read_text(encoding="utf-8"))
                reply = data.get("reply", "").strip()
                if reply:
                    REPLY_FILE.unlink()
                    if PENDING_FILE.exists():
                        PENDING_FILE.unlink()
                    return reply
            except Exception:
                pass
        time.sleep(0.5)

    log(f"  [超时] 等待回复超过 {REPLY_TIMEOUT}s，跳过")
    return None


# ─────────────────── 发送回复 ────────────────────────────────────────

def send_reply(reply_text: str):
    """把回复粘贴到输入框并发送（Ctrl+V + Enter）"""
    from config import INPUT_BOX
    pyautogui.click(INPUT_BOX[0], INPUT_BOX[1])
    time.sleep(0.3)
    pyperclip.copy(reply_text)
    keyboard.send_keys('^v')
    time.sleep(0.2)
    keyboard.send_keys('{ENTER}')
    time.sleep(0.3)


# ─────────────────── 处理单个联系人 ──────────────────────────────────

def process_contact(hwnd, win, contact_name: str):
    """
    完整处理一个有未读消息的联系人：
      打开窗口 → OCR读消息 → 请求AI回复 → 发送
    """
    log(f"▶ 处理: {contact_name}")

    activate_wechat(hwnd)
    if not open_contact_chat(win, contact_name):
        log(f"  打开聊天失败，跳过")
        return

    activate_wechat(hwnd)   # 点完再确认一次前台
    chat_img = screenshot_chat_area(win)
    messages = extract_recent_messages(chat_img, n=8)

    if not messages:
        log(f"  未识别到消息，跳过")
        return

    # 打印最后几条消息供调试
    for m in messages[-3:]:
        log(f"  [{m['speaker']}] {m['text']}")

    last = messages[-1]
    if last["speaker"] != "other":
        log(f"  最后一条是自己发的，无需回复")
        return

    log(f"  请求 AI 回复...")
    reply = request_reply(contact_name, messages)
    if not reply:
        return

    log(f"  AI回复: {reply}")
    activate_wechat(hwnd)
    send_reply(reply)
    log(f"  ✅ 已回复 {contact_name}")


# ─────────────────── 主循环 ──────────────────────────────────────────

def main():
    log("=" * 55)
    log("微信实时监控 + WorkBuddy AI 自动回复  启动")
    log(f"监控间隔: {MONITOR_INTERVAL}s  |  回复超时: {REPLY_TIMEOUT}s")
    log(f"通信目录: {COMM_DIR}")
    log("请同时运行 workbuddy_reply.py")
    log("按 Ctrl+C 停止")
    log("=" * 55)

    hwnd, win = find_wechat_window()
    if not win:
        log("❌ 未找到微信窗口，请先打开微信！")
        return

    log(f"微信窗口: {win['w']}x{win['h']} @ ({win['x']}, {win['y']})")

    # 预加载白名单和 OCR 引擎（避免首次检测时卡顿）
    load_whitelist()
    try:
        get_ocr_engine()
    except Exception as e:
        log(f"❌ PaddleOCR 初始化失败: {e}")
        return

    prev_hash = None
    # 已处理 dict: {contact_name: last_processed_time}
    # 同一联系人 60 秒内不重复处理
    processed: dict = {}
    COOLDOWN = 60

    while True:
        try:
            # 监控阶段：静默截取会话列表，不抢焦点
            session_img = screenshot_session_list(win)
            curr_hash = img_hash(session_img)

            if curr_hash == prev_hash:
                time.sleep(MONITOR_INTERVAL)
                continue

            prev_hash = curr_hash

            unread = detect_unread_contacts(session_img)

            if not unread:
                time.sleep(MONITOR_INTERVAL)
                continue

            log(f"📩 未读联系人: {unread}")

            now = time.time()
            for contact in unread:
                if contact in SKIP_CONTACTS:
                    continue
                last_time = processed.get(contact, 0)
                if now - last_time < COOLDOWN:
                    log(f"  [冷却] {contact} 距上次处理 {int(now-last_time)}s，跳过")
                    continue

                try:
                    process_contact(hwnd, win, contact)
                    processed[contact] = time.time()
                except Exception as e:
                    log(f"  [错误] 处理 {contact} 失败: {e}")

            time.sleep(MONITOR_INTERVAL)

        except KeyboardInterrupt:
            log("用户中止，退出")
            break
        except Exception as e:
            log(f"[主循环异常] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
