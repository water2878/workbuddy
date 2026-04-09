# -*- coding: utf-8 -*-
"""
微信全量导出工具 —— 一键版
  阶段1：自动滚动通讯录，截图 + OCR 获取所有联系人昵称
  阶段2：逐一搜索每个联系人，截图 + OCR 导出聊天记录（TXT + HTML）

用法：
    python wechat_all_in_one.py

输出目录（桌面）：
    微信全量导出_YYYYMMDD_HHMMSS/
        联系人昵称.txt          ← 阶段1 结果
        <联系人名>/
            <联系人名>_聊天记录.txt
            <联系人名>_聊天记录.html
            raw_screenshots/     ← 原始截图
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
pyautogui.PAUSE   = 0.05
pyautogui.FAILSAFE = True

# =====================================================================
# ★ 配置
# =====================================================================
SELF_NAME       = "我"            # 聊天记录里代表自己的名称
DESKTOP         = Path.home() / "Desktop"
OUT_ROOT        = DESKTOP / f"微信全量导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# ── 通讯录截图配置 ────────────────────────────────────────────────────
CONTACTS_MAX_SHOTS   = 500        # 通讯录最多截图张数
CONTACTS_SCROLL_STEP = -10        # 每小步滚轮量（负=向下）
CONTACTS_SCROLL_PAUSE= 0.005

# ── 聊天记录截图配置 ──────────────────────────────────────────────────
CHAT_MAX_SCROLLS  = 600           # 聊天最多翻页次数
CHAT_SCROLL_PAUSE = 0.3

# 气泡左右阈值（相对截图宽度）
LEFT_THRESH  = 0.45
RIGHT_THRESH = 0.55

# 跳过不需要导出的系统账号
SKIP_NAMES = {
    "文件传输助手", "微信团队", "腾讯新闻", "腾讯视频",
    "QQ邮件订阅", "服务通知",
}
# =====================================================================


# ══════════════════════════════════════════════════════════════════════
#  公共工具
# ══════════════════════════════════════════════════════════════════════

def img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()


def find_wechat_window():
    hwnd = 0
    for title in ["微信", "WeChat"]:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            break
    if not hwnd:
        print("❌ 未找到微信窗口，请先打开微信！")
        return None, None
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.3)
    HWND_TOPMOST = -1
    SWP_NOMOVE   = 0x0002
    SWP_NOSIZE   = 0x0001
    ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win = dict(x=rect.left, y=rect.top,
               w=rect.right - rect.left,
               h=rect.bottom - rect.top,
               hwnd=hwnd)
    print(f"✅ 微信窗口: {win['w']}x{win['h']} @ ({win['x']},{win['y']})")
    return hwnd, win


def unset_topmost(win):
    if win and win.get('hwnd'):
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        ctypes.windll.user32.SetWindowPos(
            win['hwnd'], HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


# ══════════════════════════════════════════════════════════════════════
#  阶段1：获取通讯录昵称
# ══════════════════════════════════════════════════════════════════════

def get_contacts_list_region(win):
    left = win['x'] + int(win['w'] * 0.07)
    top  = win['y'] + int(win['h'] * 0.10)
    w    = int(win['w'] * 0.20)
    h    = int(win['h'] * 0.85)
    return left, top, w, h


def click_contacts_tab(win):
    nav_x = win['x'] + int(win['w'] * 0.03)
    nav_y = win['y'] + int(win['h'] * 0.20)
    print(f"  点击通讯录图标 ({nav_x}, {nav_y})")
    pyautogui.click(nav_x, nav_y)
    time.sleep(1.5)


def scroll_to_top_contacts(cx, cy, left, top, w, h):
    pyautogui.moveTo(cx, cy)
    prev_h, stable = None, 0
    for _ in range(500):
        pyautogui.scroll(20)
        time.sleep(0.006)
        if _ % 20 == 0:
            cur_h = img_hash(pyautogui.screenshot(region=(left, top, w, h)))
            if cur_h == prev_h:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable, prev_h = 0, cur_h
    time.sleep(0.5)


def capture_contacts_screenshots(win) -> list:
    """滚动通讯录并逐屏截图，底部条带哈希连续4次相同即停止"""
    left, top, w, h = get_contacts_list_region(win)
    cx, cy = left + w // 2, top + h // 2

    print("  ⏫ 回到通讯录顶部...")
    pyautogui.click(cx, cy)
    time.sleep(0.4)
    scroll_to_top_contacts(cx, cy, left, top, w, h)
    print("  ✅ 已到顶部")

    # 校准每屏滚动格数
    print("  🔧 校准滚动量...")
    pyautogui.moveTo(cx, cy)
    shot_a = pyautogui.screenshot(region=(left, top, w, h))
    pyautogui.scroll(-1)
    time.sleep(0.20)
    shot_b = pyautogui.screenshot(region=(left, top, w, h))
    arr_a  = np.array(shot_a.convert('L'), dtype=np.int32)
    arr_b  = np.array(shot_b.convert('L'), dtype=np.int32)
    best_offset, best_score = 1, 1e9
    for off in range(1, min(100, h - 10)):
        score = np.mean(np.abs(arr_a[off:, :] - arr_b[:h - off, :]))
        if score < best_score:
            best_score, best_offset = score, off
    px_per_scroll   = max(1, best_offset)
    steps_per_screen = max(6, int(h * 0.80 / px_per_scroll))
    print(f"  每格≈{px_per_scroll}px，一屏滚{steps_per_screen}格")
    scroll_to_top_contacts(cx, cy, left, top, w, h)

    screenshots        = []
    bottom_hashes      = []
    BOTTOM_REPEAT      = 4

    print(f"  📸 截图中（最多 {CONTACTS_MAX_SHOTS} 张）...")
    for i in range(CONTACTS_MAX_SHOTS):
        time.sleep(0.20)
        shot = pyautogui.screenshot(region=(left, top, w, h))

        arr = np.array(shot)
        bh  = hashlib.md5(arr[h * 4 // 5:, :].tobytes()).hexdigest()
        bottom_hashes.append(bh)

        if len(bottom_hashes) >= BOTTOM_REPEAT and i > 0:
            if len(set(bottom_hashes[-BOTTOM_REPEAT:])) == 1:
                screenshots.append(shot)
                print(f"  第{len(screenshots):03d}张  ✅ 底部连续{BOTTOM_REPEAT}次相同，到底停止")
                break

        screenshots.append(shot)
        print(f"  第{len(screenshots):03d}张", end="\r")

        pyautogui.moveTo(cx, cy)
        for _ in range(steps_per_screen):
            pyautogui.scroll(CONTACTS_SCROLL_STEP)
            time.sleep(CONTACTS_SCROLL_PAUSE)
    else:
        print(f"\n  ⚠ 已达最大{CONTACTS_MAX_SHOTS}张，强制停止")

    print(f"\n  共截取 {len(screenshots)} 张")
    return screenshots


def ocr_contacts_page(pil_img: Image.Image, ocr_engine) -> list:
    arr    = np.array(pil_img)
    result = ocr_engine.ocr(arr, cls=False)
    if not result or not result[0]:
        return []
    blocks = []
    for item in result[0]:
        box, (text, conf) = item
        if conf < 0.5 or not text.strip():
            continue
        ys  = [pt[1] for pt in box]
        xs  = [pt[0] for pt in box]
        y_c = (min(ys) + max(ys)) / 2
        blocks.append({"text": text.strip(), "y": y_c, "x": min(xs),
                        "h": max(ys) - min(ys), "conf": conf})
    if not blocks:
        return []
    blocks.sort(key=lambda b: b["y"])
    merged, group = [], [blocks[0]]
    for b in blocks[1:]:
        ref_h = max(g["h"] for g in group) or 20
        if abs(b["y"] - group[-1]["y"]) < ref_h * 0.6:
            group.append(b)
        else:
            group.sort(key=lambda g: g["x"])
            merged.append({"text": "".join(g["text"] for g in group),
                           "y": sum(g["y"] for g in group) / len(group)})
            group = [b]
    group.sort(key=lambda g: g["x"])
    merged.append({"text": "".join(g["text"] for g in group),
                   "y": sum(g["y"] for g in group) / len(group)})
    return merged


ALPHA_ONLY   = re.compile(r'^[A-Z#0-9]$')
NOISE_WORDS  = {
    "新的朋友","仅聊天","公众号","企业微信","服务号","订阅号",
    "群聊","标签","朋友圈","设置","收藏","搜索",
    "通讯录管理","通讯录管","通讯录","联系人","企业微信联系人",
    "新朋友","添加朋友","雷达加朋友","手机联系人",
}
NOISE_PREFIX = ("》",">","√","✓","V","通讯录","联系人","<>")
NOISE_KW     = ["查看内容","选择文件","<>变更","变更预览"]

def is_valid_nickname(text: str) -> bool:
    t = text.strip()
    if not t or ALPHA_ONLY.match(t): return False
    clean = t
    for p in NOISE_PREFIX:
        if clean.startswith(p):
            clean = clean[len(p):].strip()
    if not clean or clean in NOISE_WORDS or t in NOISE_WORDS: return False
    for kw in NOISE_KW:
        if kw in t: return False
    if re.match(r'^\d+$', t): return False
    if not re.search(r'[\w\u4e00-\u9fff]', t): return False
    if len(t) <= 2 and not re.search(r'[\u4e00-\u9fff]', t): return False
    return True


def stage1_get_contacts(win) -> list:
    print("\n" + "="*55)
    print("  阶段1：获取通讯录联系人昵称")
    print("="*55)

    click_contacts_tab(win)
    screenshots = capture_contacts_screenshots(win)

    print("\n  🔤 OCR 识别通讯录...")
    import paddleocr
    ocr = paddleocr.PaddleOCR(use_angle_cls=False, lang='ch',
                               use_gpu=False, show_log=False)

    all_lines = []
    for i, shot in enumerate(screenshots):
        lines = ocr_contacts_page(shot, ocr)
        all_lines.extend(l["text"] for l in lines)

    # 去重 + 过滤
    seen, nicknames = set(), []
    for name in all_lines:
        name = name.strip()
        if name and name not in seen and is_valid_nickname(name):
            if name not in SKIP_NAMES:
                seen.add(name)
                nicknames.append(name)

    # 保存
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    contacts_file = OUT_ROOT / "联系人昵称.txt"
    contacts_file.write_text("\n".join(nicknames), encoding="utf-8")

    print(f"\n  ✅ 识别到 {len(nicknames)} 个联系人")
    print(f"  已保存 → {contacts_file}")
    for n in nicknames[:20]:
        print(f"    {n}")
    if len(nicknames) > 20:
        print(f"    ... 共 {len(nicknames)} 个")

    return nicknames


# ══════════════════════════════════════════════════════════════════════
#  阶段2：逐一导出聊天记录
# ══════════════════════════════════════════════════════════════════════

def get_chat_region(win):
    """
    动态检测聊天气泡区域：扫描灰色分隔线确定真实边界。
    水平扫描中间行 → 竖向分隔线右侧 = 聊天区左边界；
    垂直从底部往上扫 → 横向分隔线上侧 = 聊天区底边界。
    """
    wx, wy, ww, wh = win['x'], win['y'], win['w'], win['h']
    shot = pyautogui.screenshot(region=(wx, wy, ww, wh))
    arr = np.array(shot.convert('RGB'))

    def is_sep(pixel):
        r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
        return max(abs(r - g), abs(g - b), abs(r - b)) < 15 and 160 <= r <= 245

    # 水平扫描多行 → 竖向分隔线
    chat_left_rel = None
    for scan_frac in [0.50, 0.40, 0.60, 0.35, 0.65]:
        scan_y = int(wh * scan_frac)
        row = arr[scan_y, :, :]
        for x in range(int(ww * 0.15), int(ww * 0.60)):
            if is_sep(row[x]):
                x2 = x
                while x2 < int(ww * 0.60) and is_sep(row[x2]):
                    x2 += 1
                if 1 <= (x2 - x) <= 12:
                    chat_left_rel = x2
                    break
        if chat_left_rel is not None:
            break
    if chat_left_rel is None:
        chat_left_rel = int(ww * 0.33)

    # 垂直从底部往上扫 → 横向分隔线
    scan_x = chat_left_rel + (ww - chat_left_rel) // 2
    col = arr[:, scan_x, :]
    chat_bottom_rel = None
    for y in range(int(wh * 0.92), int(wh * 0.75), -1):
        if is_sep(col[y]):
            y2 = y
            while y2 > int(wh * 0.50) and is_sep(col[y2]):
                y2 -= 1
            if 1 <= (y - y2) <= 10:
                chat_bottom_rel = y2
                break
    if chat_bottom_rel is None:
        chat_bottom_rel = int(wh * 0.72)

    title_h = max(50, int(wh * 0.08))
    left = wx + chat_left_rel + 2
    top  = wy + title_h
    w    = ww - chat_left_rel - 4
    h    = chat_bottom_rel - title_h
    return left, top, w, h


def search_and_open_contact(win, keyword):
    print(f"  🔍 搜索: {keyword}")
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.8)
    pyperclip.copy(keyword)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(1.2)
    pyautogui.press('enter')
    time.sleep(2.0)


def capture_chat_screenshots(win) -> list:
    left, top, w, h = get_chat_region(win)
    cx, cy = left + w // 2, top + h // 2

    pyautogui.click(cx, cy)
    time.sleep(0.5)

    print("  ⏫ Ctrl+Home 跳到最顶部...")
    pyautogui.hotkey('ctrl', 'Home')
    time.sleep(3.0)
    for _ in range(3):
        pyautogui.hotkey('ctrl', 'Home')
        time.sleep(0.8)

    screenshots  = []
    seen_hashes  = set()
    repeat_count = 0

    for i in range(CHAT_MAX_SCROLLS):
        shot      = pyautogui.screenshot(region=(left, top, w, h))
        curr_hash = img_hash(shot)

        if curr_hash in seen_hashes:
            repeat_count += 1
            if repeat_count >= 4:
                print(f"\n  ✅ 到达底部（连续{repeat_count}次重复）")
                break
        else:
            repeat_count = 0
            seen_hashes.add(curr_hash)
            screenshots.append(shot)
            print(f"  第{len(screenshots):03d}页", end="\r")

        pyautogui.click(cx, cy)
        pyautogui.press('pagedown')
        time.sleep(CHAT_SCROLL_PAUSE)

    print(f"\n  共截取 {len(screenshots)} 页")
    return screenshots


# ── OCR 文本处理 ─────────────────────────────────────────────────────

def fix_text(text: str) -> str:
    text = re.sub(r'(\d)\s+(\d)',                                    r'\1\2',  text)
    text = re.sub(r'(\d)\s*[：:]\s*(\d)',                            r'\1:\2', text)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff，。！？：；、])', '', text)
    text = re.sub(r'(?<=[，。！？：；、])\s+(?=[\u4e00-\u9fff])',     '', text)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[a-zA-Z0-9])',        '', text)
    text = re.sub(r'(?<=[a-zA-Z0-9])\s+(?=[\u4e00-\u9fff])',        '', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

NOISE_PATS_CHAT = [
    re.compile(r'^你已添加了'),
    re.compile(r'已在其[他它].*设.*接听'),
    re.compile(r'^[^\u4e00-\u9fff\w]+$'),
    re.compile(r'^\d{1,3}$'),
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

def is_chat_noise(t: str) -> bool:
    t = t.strip()
    if not t: return True
    if len(t) <= 2 and not re.search(r'[\u4e00-\u9fff]', t): return True
    for p in NOISE_PATS_CHAT:
        if p.search(t): return True
    return False

def is_timestamp(t: str) -> bool:
    return any(p.match(t.strip()) for p in TS_PATS)

def classify_speaker(x_center: float, img_w: int) -> str:
    r = x_center / img_w
    if r < LEFT_THRESH:  return "other"
    if r > RIGHT_THRESH: return "self"
    return "center"


def ocr_chat_page(pil_img: Image.Image, page_idx: int, ocr_engine) -> list:
    w, h     = pil_img.size
    pil_up   = pil_img.resize((w * 2, h * 2), Image.LANCZOS)
    img_w    = w * 2
    img_arr  = np.array(pil_up)
    result   = ocr_engine.ocr(img_arr, cls=False)
    if not result or not result[0]:
        return []

    msgs = []
    for item in result[0]:
        box, (text, conf) = item
        if conf < 0.5: continue
        text = fix_text(text)
        if not text or is_chat_noise(text): continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x_c, y_c = sum(xs) / 4, sum(ys) / 4
        if is_timestamp(text):
            mtype, speaker = "timestamp", None
        else:
            speaker = classify_speaker(x_c, img_w)
            mtype   = "timestamp" if speaker == "center" else "message"
            if mtype == "timestamp": speaker = None
        msgs.append({"text": text, "type": mtype, "speaker": speaker,
                     "page": page_idx, "y": y_c, "x": x_c})
    msgs.sort(key=lambda m: m["y"])
    return msgs


def deduplicate_chat(messages: list) -> list:
    if not messages: return []
    deduped, prev = [], ""
    for m in messages:
        if m["text"] != prev:
            deduped.append(m)
            prev = m["text"]
    from collections import Counter
    counts = Counter(m["text"] for m in deduped)
    high   = {t for t, c in counts.items() if c >= 6}
    return [m for m in deduped if m["text"] not in high]


# ── 保存 ─────────────────────────────────────────────────────────────

def save_txt(messages, path, target_name, self_name, other_name):
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


def save_html(messages, path, target_name, self_name, other_name):
    msg_count = sum(1 for m in messages if m["type"] == "message")
    rows = []
    for m in messages:
        t = (m["text"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
        if m["type"] == "timestamp":
            rows.append(f'<div class="ts">{t}</div>')
        elif m["speaker"] == "self":
            rows.append(f'<div class="msg self"><span class="bubble self-b">{t}</span>'
                        f'<span class="name">{self_name}</span></div>')
        else:
            rows.append(f'<div class="msg other"><span class="name">{other_name}</span>'
                        f'<span class="bubble other-b">{t}</span></div>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{target_name}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Microsoft YaHei",sans-serif;background:#ededed;padding:16px}}
.wrap{{max-width:700px;margin:0 auto;background:#f5f5f5;border-radius:8px;
       box-shadow:0 1px 4px rgba(0,0,0,.15);padding-bottom:20px}}
.header{{background:#f5f5f5;border-bottom:1px solid #d9d9d9;padding:13px 20px;
          font-size:16px;font-weight:500;text-align:center}}
.meta{{text-align:center;font-size:12px;color:#aaa;padding:8px 0 10px}}
.ts{{text-align:center;font-size:12px;color:#b2b2b2;padding:10px 0 4px}}
.msg{{display:flex;align-items:flex-start;padding:5px 16px;gap:8px}}
.msg.other{{flex-direction:row}}.msg.self{{flex-direction:row-reverse}}
.name{{font-size:12px;color:#999;white-space:nowrap;padding-top:6px;min-width:24px}}
.bubble{{display:inline-block;font-size:14px;line-height:1.7;padding:8px 12px;
          max-width:68%;word-break:break-all;white-space:pre-wrap;
          box-shadow:0 1px 2px rgba(0,0,0,.08)}}
.other-b{{background:#fff;color:#191919;border-radius:4px 12px 12px 12px}}
.self-b{{background:#95ec69;color:#191919;border-radius:12px 4px 12px 12px}}
</style></head><body>
<div class="wrap">
  <div class="header">💬 {target_name}</div>
  <div class="meta">共 {msg_count} 条消息 · 导出于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  {''.join(rows)}
</div></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def export_one_contact(win, name: str, ocr_engine):
    print(f"\n{'─'*50}")
    print(f"  导出: {name}")
    print(f"{'─'*50}")

    safe    = re.sub(r'[\\/:*?"<>|]', '_', name)
    out_dir = OUT_ROOT / safe
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_screenshots"
    raw_dir.mkdir(exist_ok=True)

    search_and_open_contact(win, name)
    screenshots = capture_chat_screenshots(win)

    print("  💾 保存原始截图...")
    for i, s in enumerate(screenshots):
        s.save(raw_dir / f"page_{i+1:04d}.png")

    print("  🔤 OCR 识别中...")
    all_msgs = []
    for i, shot in enumerate(screenshots):
        msgs   = ocr_chat_page(shot, i, ocr_engine)
        n_msg  = sum(1 for m in msgs if m["type"] == "message")
        n_ts   = sum(1 for m in msgs if m["type"] == "timestamp")
        print(f"  [{i+1:03d}/{len(screenshots)}] 消息{n_msg} 时间戳{n_ts}", end="\r")
        all_msgs.extend(msgs)

    print(f"\n  去重前 {len(all_msgs)} 行...", end="")
    all_msgs = deduplicate_chat(all_msgs)
    print(f" 去重后 {len(all_msgs)} 行")

    txt_path  = out_dir / f"{safe}_聊天记录.txt"
    html_path = out_dir / f"{safe}_聊天记录.html"
    save_txt(all_msgs,  txt_path,  name, SELF_NAME, name)
    save_html(all_msgs, html_path, name, SELF_NAME, name)

    msg_count = sum(1 for m in all_msgs if m["type"] == "message")
    print(f"  ✅ 完成  {msg_count} 条消息")
    print(f"     TXT  → {txt_path}")
    print(f"     HTML → {html_path}")
    return msg_count


# ══════════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  微信全量导出 —— 一键版")
    print("=" * 55)

    hwnd, win = find_wechat_window()
    if not win:
        return

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"📁 输出目录: {OUT_ROOT}\n")

    # ── 阶段1：获取联系人昵称 ────────────────────────────────────────
    nicknames = stage1_get_contacts(win)

    if not nicknames:
        print("❌ 未识别到任何联系人，退出")
        return

    print(f"\n即将导出 {len(nicknames)} 个联系人的聊天记录...")
    print("（3秒后开始，请勿操作鼠标键盘）")
    time.sleep(3)

    # ── 阶段2：逐一导出聊天记录 ─────────────────────────────────────
    print("\n" + "=" * 55)
    print("  阶段2：批量导出聊天记录")
    print("=" * 55)

    # 初始化 OCR（只初始化一次，全程复用）
    print("🔤 初始化 PaddleOCR...")
    import paddleocr
    ocr = paddleocr.PaddleOCR(use_angle_cls=False, lang='ch',
                               use_gpu=False, show_log=False)
    print("  ✅ PaddleOCR 就绪\n")

    results = []
    for idx, name in enumerate(nicknames, 1):
        print(f"\n[{idx}/{len(nicknames)}] {name}")
        try:
            count = export_one_contact(win, name, ocr)
            results.append((name, count, "✅"))
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            results.append((name, 0, f"❌ {e}"))

    # ── 汇总报告 ────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("  全部完成！汇总：")
    print(f"{'='*55}")
    ok    = [r for r in results if r[2].startswith("✅")]
    fail  = [r for r in results if not r[2].startswith("✅")]
    total = sum(r[1] for r in ok)
    for name, count, status in results:
        print(f"  {status}  {name}  —  {count} 条")
    print(f"\n  成功 {len(ok)} 个 / 失败 {len(fail)} 个 / 共 {total} 条消息")
    print(f"  📁 {OUT_ROOT}")

    unset_topmost(win)

    import os as _os
    _os.startfile(OUT_ROOT)


if __name__ == "__main__":
    main()
