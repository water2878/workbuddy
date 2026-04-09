# -*- coding: utf-8 -*-
"""
微信聊天记录导出工具
  1. Ctrl+F 搜索联系人，自动进入聊天窗口
  2. Ctrl+Home 跳到最顶部，然后 Page Down 逐页截图（无重叠）
  3. PaddleOCR 2.9.1 CPU推理识别文字 + 行坐标判断左右气泡（区分发言人）
  4. 输出 txt + html 双格式

用法：
    python export_chat.py
"""

import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['FLAGS_use_mkldnn'] = '0'

import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time, re, ctypes, ctypes.wintypes, hashlib, warnings
from datetime import datetime
from pathlib import Path

import pyautogui
import pyperclip
import numpy as np
from PIL import Image

warnings.filterwarnings('ignore')
pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = False

# =====================================================================
# ★ 配置
# =====================================================================

# ── 从昵称文件动态读取联系人列表 ────────────────────────────────────
# 每行一个昵称；跳过空行和系统账号
_CONTACTS_FILE = Path.home() / "Desktop" / "微信联系人昵称.txt"
_SKIP = {"微信团队", "文件传输助手", "腾讯新闻", "腾讯视频", "QQ邮件订阅", "服务通知"}

# 过滤明显残缺行（单字符、纯括号等）
def _valid(name: str) -> bool:
    import re as _re
    n = name.strip()
    if not n or len(n) == 1: return False
    if n in _SKIP: return False
    if _re.fullmatch(r'[（）()\[\]{}\s\-~·•]+', n): return False
    return True

if _CONTACTS_FILE.exists():
    _raw = _CONTACTS_FILE.read_text(encoding="utf-8").splitlines()
    CONTACTS = [(n.strip(), "我", n.strip()) for n in _raw if _valid(n.strip())]
    print(f"📋 从昵称文件读取到 {len(CONTACTS)} 个联系人")
else:
    # 文件不存在时回退到手动列表
    CONTACTS = [
        ("李玉娇", "我", "李玉娇"),
    ]
    print(f"⚠ 未找到 {_CONTACTS_FILE}，使用手动列表")

DESKTOP      = Path.home() / "Desktop"
BATCH_DIR    = DESKTOP / f"微信批量导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

SCROLL_PAUSE = 0.3    # 每次翻页后等待（秒）
MAX_SCROLLS  = 600    # 最多翻页次数

# 气泡位置阈值（相对截图宽度比例）
LEFT_THRESH  = 0.45   # x中心 < 45% → 对方（左边）
RIGHT_THRESH = 0.55   # x中心 > 55% → 自己（右边）
# =====================================================================


# ─────────────────────── 微信窗口 ────────────────────────────────────

def find_wechat_window():
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
               w=rect.right - rect.left,
               h=rect.bottom - rect.top)
    print(f"✅ 微信窗口: {win['w']}x{win['h']} at ({win['x']}, {win['y']})")
    return hwnd, win


def search_and_open_contact(win, keyword):
    """Ctrl+F 搜索联系人并回车进入"""
    print(f"🔍 搜索: {keyword}")
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.8)
    pyperclip.copy(keyword)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(1.2)
    pyautogui.press('enter')
    time.sleep(2.0)
    print("  ✅ 已进入聊天窗口")


def get_chat_region(win):
    """
    动态检测微信聊天气泡区域 (left, top, w, h)。

    原理：
      1. 截取微信整窗口截图
      2. 水平扫描中间行像素
         → 找到灰色竖向分隔线（左侧面板|聊天区）
         → 分隔线右侧 = 聊天区真实左边界
      3. 垂直扫描从底部往上
         → 找到灰色横向分隔线（聊天区|输入框）
         → 分隔线上侧 = 聊天区真实底部边界
      4. 组合出精确的截图区域
      5. 找不到时降级为固定比例兜底
    """
    wx, wy, ww, wh = win['x'], win['y'], win['w'], win['h']

    shot = pyautogui.screenshot(region=(wx, wy, ww, wh))
    arr = np.array(shot.convert('RGB'))  # shape: (wh, ww, 3)

    # 灰色判定：R≈G≈B，且亮度在 160~245 之间（微信分隔线颜色）
    def is_sep(pixel):
        r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
        return max(abs(r - g), abs(g - b), abs(r - b)) < 15 and 160 <= r <= 245

    # ── 1. 水平扫描中间行 → 找竖向分隔线右侧边缘 ─────────────────
    # 多扫几行取众数，避免单行噪声
    chat_left_rel = None
    for scan_frac in [0.50, 0.40, 0.60, 0.35, 0.65]:
        scan_y = int(wh * scan_frac)
        row = arr[scan_y, :, :]
        x_start = int(ww * 0.15)
        x_end   = int(ww * 0.60)
        for x in range(x_start, x_end):
            if is_sep(row[x]):
                x2 = x
                while x2 < x_end and is_sep(row[x2]):
                    x2 += 1
                sep_width = x2 - x
                if 1 <= sep_width <= 12:   # 分隔线宽度合理
                    chat_left_rel = x2      # 分隔线右侧即聊天区起始
                    break
        if chat_left_rel is not None:
            break

    if chat_left_rel is None:
        chat_left_rel = int(ww * 0.33)
        print(f"  ⚠ 未检测到竖向分隔线，使用默认左边界 {chat_left_rel}px")
    else:
        print(f"  ✅ 检测到聊天区左边界: x={chat_left_rel}px (占窗口 {chat_left_rel/ww:.0%})")

    # ── 2. 垂直扫描从底部往上 → 找横向分隔线上侧边缘 ─────────────
    # 在聊天区水平中部取一列
    scan_x = chat_left_rel + (ww - chat_left_rel) // 2
    col = arr[:, scan_x, :]

    chat_bottom_rel = None
    y_start = int(wh * 0.92)
    y_end   = int(wh * 0.75)
    for y in range(y_start, y_end, -1):
        if is_sep(col[y]):
            y2 = y
            while y2 > y_end and is_sep(col[y2]):
                y2 -= 1
            sep_height = y - y2
            if 1 <= sep_height <= 10:
                chat_bottom_rel = y2    # 分隔线上侧即聊天区底部
                break

    if chat_bottom_rel is None:
        chat_bottom_rel = int(wh * 0.78)
        print(f"  ⚠ 未检测到横向分隔线，使用默认底部边界 {chat_bottom_rel}px")
    else:
        print(f"  ✅ 检测到聊天区底边界: y={chat_bottom_rel}px (占窗口 {chat_bottom_rel/wh:.0%})")

    # ── 3. 顶部：跳过标题栏+联系人名称行 ─────────────────────────
    title_h = max(50, int(wh * 0.08))

    # ── 4. 组合最终区域 ────────────────────────────────────────────
    left = wx + chat_left_rel + 2
    top  = wy + title_h
    w    = ww - chat_left_rel - 4
    h    = chat_bottom_rel - title_h

    return left, top, w, h


def img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()


def scroll_and_capture(win) -> list:
    """
    先 Ctrl+Home 跳到最顶部，
    然后用 Page Down 逐页截图（每次精确翻一整屏，无重叠）
    """
    left, top, w, h = get_chat_region(win)
    cx, cy = left + w // 2, top + h // 2

    # 点击聊天区域获取焦点
    pyautogui.click(cx, cy)
    time.sleep(0.5)

    # ── 跳到最顶部 ──────────────────────────────────
    print("⏫ 正在跳到最顶部（Ctrl+Home）...")
    pyautogui.hotkey('ctrl', 'Home')
    time.sleep(3.0)

    # 再按几次确保加载完毕
    for _ in range(3):
        pyautogui.hotkey('ctrl', 'Home')
        time.sleep(0.8)

    screenshots = []
    seen_hashes = set()   # 全局去重：同一画面只保存一次
    repeat_count = 0      # 连续"已见过"的帧数，用于判断到底

    print(f"📸 开始逐页截图（Page Down 精确翻页，最多 {MAX_SCROLLS} 页）...")

    for i in range(MAX_SCROLLS):
        shot = pyautogui.screenshot(region=(left, top, w, h))
        curr_hash = img_hash(shot)

        if curr_hash in seen_hashes:
            repeat_count += 1
            print(f"  跳过重复 ({repeat_count}) (hash: {curr_hash[:8]}...)", end="\r")
            if repeat_count >= 4:
                print(f"\n  ✅ 已到达底部（连续 {repeat_count} 次重复画面）")
                break
        else:
            repeat_count = 0
            seen_hashes.add(curr_hash)
            screenshots.append(shot)
            print(f"  第 {len(screenshots):03d} 页 (hash: {curr_hash[:8]}...)")

        # Page Down = 精确翻一整屏
        pyautogui.click(cx, cy)
        pyautogui.press('pagedown')
        time.sleep(SCROLL_PAUSE)

    print(f"  共截取 {len(screenshots)} 页")
    return screenshots


# ─────────────────────── PaddleOCR ───────────────────────────────────

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        print("🔤 初始化 PaddleOCR（首次运行会下载模型）...")
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            use_angle_cls=False,
            lang='ch',
            use_gpu=False,
            show_log=False,
        )
        print("  ✅ PaddleOCR 初始化完成")
    return _ocr_engine


def ocr_page(pil_img: Image.Image, page_idx: int) -> list:
    """对单张截图做 PaddleOCR，返回结构化消息列表"""
    ocr = get_ocr_engine()

    # 放大 2x 提升识别率
    w, h = pil_img.size
    pil_up = pil_img.resize((w * 2, h * 2), Image.LANCZOS)
    img_w = w * 2
    img_arr = np.array(pil_up)

    result = ocr.ocr(img_arr, cls=False)
    if not result or not result[0]:
        return []

    msgs = []
    for item in result[0]:
        box, (text, conf) = item
        if conf < 0.5:
            continue
        text = fix_text(text)
        if not text or is_noise(text):
            continue

        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x_center = sum(xs) / 4
        y_center = sum(ys) / 4

        if is_timestamp(text):
            mtype, speaker = "timestamp", None
        else:
            speaker = classify_speaker(x_center, img_w)
            if speaker == "center":
                mtype, speaker = "timestamp", None
            else:
                mtype = "message"

        msgs.append({
            "text":    text,
            "type":    mtype,
            "speaker": speaker,
            "page":    page_idx,
            "y":       y_center,
            "x":       x_center,
        })

    # 按 y 坐标排序
    msgs.sort(key=lambda m: m["y"])
    return msgs


# ─────────────────────── 文本处理 ────────────────────────────────────

def fix_text(text: str) -> str:
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    text = re.sub(r'(\d)\s*[：:]\s*(\d)', r'\1:\2', text)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff，。！？：；、])', '', text)
    text = re.sub(r'(?<=[，。！？：；、])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[a-zA-Z0-9])', '', text)
    text = re.sub(r'(?<=[a-zA-Z0-9])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


NOISE_PATS = [
    re.compile(r'^你已添加了'),
    re.compile(r'已在其[他它].*设.*接听'),
    re.compile(r'^[^\u4e00-\u9fff\w]+$'),
    re.compile(r'^\d{1,3}$'),
    re.compile(r'^AiLy\s*李\d+$'),
    re.compile(r'^微信$'),
]

TS_PATS = [
    re.compile(r'^星期[一二三四五六日]\s*\d{1,2}:\d{2}$'),
    re.compile(r'^[昨今]天\s*\d{1,2}:\d{2}$'),
    re.compile(r'^\d{1,2}:\d{2}$'),
    re.compile(r'^\d{4}-\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2}$'),
    re.compile(r'^[\u4e00-\u9fff]{1,6}\s*\d{1,2}:\d{2}$'),
    re.compile(r'^\d月\d{1,2}日'),
]


def is_noise(t: str) -> bool:
    t = t.strip()
    if not t: return True
    if len(t) <= 2 and not re.search(r'[\u4e00-\u9fff]', t): return True
    for p in NOISE_PATS:
        if p.search(t): return True
    return False


def is_timestamp(t: str) -> bool:
    for p in TS_PATS:
        if p.match(t.strip()): return True
    return False


def classify_speaker(x_center: float, img_w: int) -> str:
    r = x_center / img_w
    if r < LEFT_THRESH:  return "other"
    if r > RIGHT_THRESH: return "self"
    return "center"


def deduplicate(messages: list) -> list:
    if not messages: return []
    deduped, prev = [], ""
    for m in messages:
        if m["text"] != prev:
            deduped.append(m)
            prev = m["text"]
    from collections import Counter
    counts = Counter(m["text"] for m in deduped)
    high = {t for t, c in counts.items() if c >= 6}
    if high:
        print(f"  [去重] 过滤 {len(high)} 个高频重复行")
    return [m for m in deduped if m["text"] not in high]


# ─────────────────────── 保存输出 ─────────────────────────────────────

def save_txt(messages: list, path: Path, target_name: str, self_name: str, other_name: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"微信聊天记录 - {target_name}\n")
        f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        for m in messages:
            if m["type"] == "timestamp":
                f.write(f"\n── {m['text']} ──\n\n")
            elif m["speaker"] == "self":
                f.write(f"[{self_name}] {m['text']}\n")
            else:
                f.write(f"[{other_name}] {m['text']}\n")


def save_html(messages: list, path: Path, target_name: str, self_name: str, other_name: str):
    msg_count = sum(1 for m in messages if m["type"] == "message")
    rows = []
    for m in messages:
        text = (m["text"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        if m["type"] == "timestamp":
            rows.append(f'<div class="ts">{text}</div>')
        elif m["speaker"] == "self":
            rows.append(
                f'<div class="msg self">'
                f'<span class="bubble self-b">{text}</span>'
                f'<span class="name">{self_name}</span>'
                f'</div>'
            )
        else:
            rows.append(
                f'<div class="msg other">'
                f'<span class="name">{other_name}</span>'
                f'<span class="bubble other-b">{text}</span>'
                f'</div>'
            )

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>聊天记录 - {target_name}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#ededed;padding:16px;min-height:100vh}}
.wrap{{max-width:700px;margin:0 auto;background:#f5f5f5;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.15);overflow:hidden;padding-bottom:20px}}
.header{{background:#f5f5f5;border-bottom:1px solid #d9d9d9;padding:13px 20px;font-size:16px;font-weight:500;color:#191919;text-align:center}}
.meta{{text-align:center;font-size:12px;color:#aaa;padding:8px 0 10px}}
.ts{{text-align:center;font-size:12px;color:#b2b2b2;padding:10px 0 4px;user-select:none}}
.msg{{display:flex;align-items:flex-start;padding:5px 16px;gap:8px}}
.msg.other{{flex-direction:row}}
.msg.self{{flex-direction:row-reverse}}
.name{{font-size:12px;color:#999;white-space:nowrap;padding-top:6px;min-width:24px}}
.bubble{{display:inline-block;font-size:14px;line-height:1.7;padding:8px 12px;max-width:68%;word-break:break-all;white-space:pre-wrap;box-shadow:0 1px 2px rgba(0,0,0,.08)}}
.other-b{{background:#fff;color:#191919;border-radius:4px 12px 12px 12px}}
.self-b{{background:#95ec69;color:#191919;border-radius:12px 4px 12px 12px}}
</style>
</head><body>
<div class="wrap">
  <div class="header">💬 {target_name}</div>
  <div class="meta">共 {msg_count} 条消息 · 导出于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  {''.join(rows)}
</div>
</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# ─────────────────────── 主流程 ──────────────────────────────────────

def export_one(win, target_name: str, self_name: str, other_name: str):
    """导出单个联系人的聊天记录"""
    print(f"\n{'='*55}")
    print(f"  导出联系人: {target_name}")
    print(f"{'='*55}")

    output_dir = BATCH_DIR / target_name
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw_screenshots"
    raw_dir.mkdir(exist_ok=True)

    # 搜索并打开联系人
    search_and_open_contact(win, target_name)
    time.sleep(1.5)

    # 截图
    screenshots = scroll_and_capture(win)

    # 保存原始截图
    print("💾 保存截图...")
    for i, shot in enumerate(screenshots):
        shot.save(raw_dir / f"page_{i+1:04d}.png")
    print(f"  已保存 {len(screenshots)} 张")

    # OCR 识别
    print("\n🔤 PaddleOCR 识别中...")
    all_msgs = []
    for i, shot in enumerate(screenshots):
        print(f"  [{i+1:03d}/{len(screenshots)}]", end="  ", flush=True)
        msgs = ocr_page(shot, i)
        n_msg = sum(1 for m in msgs if m["type"] == "message")
        n_ts  = sum(1 for m in msgs if m["type"] == "timestamp")
        print(f"消息 {n_msg} / 时间戳 {n_ts}")
        all_msgs.extend(msgs)

    print(f"\n共 {len(all_msgs)} 行，去重中...")
    all_msgs = deduplicate(all_msgs)
    print(f"去重后 {len(all_msgs)} 行")

    # 保存结果
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', target_name)  # 文件名安全处理
    txt_path  = output_dir / f"{safe_name}_聊天记录.txt"
    html_path = output_dir / f"{safe_name}_聊天记录.html"
    save_txt(all_msgs, txt_path, target_name, self_name, other_name)
    save_html(all_msgs, html_path, target_name, self_name, other_name)

    print(f"\n✅ [{target_name}] 完成！")
    print(f"  TXT  → {txt_path}")
    print(f"  HTML → {html_path}")
    return len(all_msgs)


def main():
    print("=" * 55)
    print("  微信聊天记录批量导出（PaddleOCR 2.9.1 CPU）")
    print(f"  共 {len(CONTACTS)} 个联系人")
    print("=" * 55)

    # 找微信窗口（只找一次）
    hwnd, win = find_wechat_window()
    if not win:
        return

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 输出目录: {BATCH_DIR}")

    results = []
    for idx, contact in enumerate(CONTACTS, 1):
        target_name, self_name, other_name = contact
        print(f"\n[{idx}/{len(CONTACTS)}] 开始导出: {target_name}")
        try:
            count = export_one(win, target_name, self_name, other_name)
            results.append((target_name, count, "✅"))
        except Exception as e:
            print(f"❌ [{target_name}] 导出失败: {e}")
            results.append((target_name, 0, f"❌ {e}"))

    # 汇总报告
    print(f"\n{'='*55}")
    print("  批量导出完成！汇总：")
    print(f"{'='*55}")
    for name, count, status in results:
        print(f"  {status} {name} — {count} 条消息")
    print(f"\n📁 所有文件保存在: {BATCH_DIR}")

    import os as _os
    _os.startfile(BATCH_DIR)


if __name__ == "__main__":
    main()
