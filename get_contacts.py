# -*- coding: utf-8 -*-
"""
微信通讯录昵称抓取工具
  1. 自动打开微信通讯录
  2. Page Down 逐页截图（全局去重）
  3. PaddleOCR 识别所有昵称
  4. 输出到 contacts.txt，格式可直接粘贴进 export_chat.py 的 CONTACTS 列表
"""

import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['FLAGS_use_mkldnn'] = '0'

import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time, re, ctypes, ctypes.wintypes, hashlib, warnings
from pathlib import Path
from datetime import datetime

import pyautogui
import numpy as np
from PIL import Image

warnings.filterwarnings('ignore')

pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = False

# =====================================================================
# ★ 配置
# =====================================================================
SCROLL_PAUSE  = 0.02   # 每小步滚动后等待（秒）—— 稍长，让微信有时间渲染
SCROLL_STEP   = -10    # 每小步滚轮量（负=向下，加倍）
# 每次截图后需要滚动的"格数"，自动校准为刚好一整屏
# 实测：每格 scroll(-1) ≈ 40px，截图区域高约 600px → 15格≈一屏
# 用 AUTO_CALIBRATE=True 时脚本会自动测量，否则用下面的固定值
SCROLL_STEPS_PER_SHOT = 18   # 每张截图后滚动步数（一屏不重叠）
MAX_SHOTS     = 500    # 最多截图张数
OUTPUT_FILE   = Path.home() / "Desktop" / "微信联系人昵称.txt"
# =====================================================================


# ─────────────────────── 微信窗口 ────────────────────────────────────

def find_wechat_window():
    hwnd = 0
    for title in ["微信", "WeChat"]:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            break
    if not hwnd:
        print("❌ 未找到微信窗口，请先打开微信！")
        return None, None
    # 恢复窗口（防止最小化）
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.3)
    # 置为最顶层，确保截图时不被其他窗口遮挡
    HWND_TOPMOST = -1
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    win = dict(x=rect.left, y=rect.top,
               w=rect.right - rect.left,
               h=rect.bottom - rect.top,
               hwnd=hwnd)
    print(f"✅ 微信窗口: {win['w']}x{win['h']} at ({win['x']}, {win['y']})")
    return hwnd, win


def click_contacts_tab(win):
    """
    点击左侧通讯录图标（第二个图标，约在左侧导航栏 20% 高度处）
    微信PC版左侧导航栏图标顺序：聊天 / 通讯录 / 收藏 / 朋友圈...
    """
    nav_x = win['x'] + int(win['w'] * 0.03)   # 左侧导航栏中心 x（导航栏约60px宽，取中心）
    nav_y = win['y'] + int(win['h'] * 0.20)   # 通讯录图标（第2个图标，用户截图确认约20%高度处）
    print(f"📒 点击通讯录图标 ({nav_x}, {nav_y})")
    pyautogui.click(nav_x, nav_y)
    time.sleep(1.5)


def get_contacts_list_region(win):
    """
    通讯录列表区域：左侧面板（约占窗口宽度 7%~27%）
    """
    left = win['x'] + int(win['w'] * 0.07)
    top  = win['y'] + int(win['h'] * 0.10)
    w    = int(win['w'] * 0.20)
    h    = int(win['h'] * 0.85)
    return left, top, w, h


def img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()


def center_hash(img: Image.Image) -> str:
    """只对图片中间 1/4 ~ 3/4 纵向区域取哈希，避免顶部字母索引行不变导致误判底部"""
    arr = np.array(img)
    h = arr.shape[0]
    strip = arr[h//4 : h*3//4, :]
    return hashlib.md5(strip.tobytes()).hexdigest()


def get_scrollbar_pos(hwnd_list) -> tuple:
    """
    通过 Windows API 读取列表子窗口的滚动条位置。
    返回 (nPos, nMax)；失败返回 (0, 1)。
    """
    SB_VERT = 1
    class SCROLLINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("fMask",  ctypes.c_uint),
            ("nMin",   ctypes.c_int),
            ("nMax",   ctypes.c_int),
            ("nPage",  ctypes.c_uint),
            ("nPos",   ctypes.c_int),
            ("nTrackPos", ctypes.c_int),
        ]
    SIF_ALL = 0x17
    si = SCROLLINFO()
    si.cbSize = ctypes.sizeof(SCROLLINFO)
    si.fMask  = SIF_ALL
    ok = ctypes.windll.user32.GetScrollInfo(hwnd_list, SB_VERT, ctypes.byref(si))
    if ok:
        usable_max = max(1, si.nMax - int(si.nPage) + 1)
        return si.nPos, usable_max
    return 0, 1


def find_contacts_list_hwnd(win_hwnd) -> int:
    """
    枚举微信窗口的所有子窗口，找到通讯录列表控件句柄。
    微信通讯录列表通常是 ListBox 或某个可滚动子窗口。
    """
    found = []

    EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_long)

    def enum_cb(hwnd, lParam):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        cls = buf.value
        # 微信联系人列表是 WTWindow / DirectUIHWND / 或 ListBox
        if cls in ("WTWindow", "DirectUIHWND", "ListBox", "SysListView32"):
            found.append(hwnd)
        return True

    cb = EnumChildProc(enum_cb)
    ctypes.windll.user32.EnumChildWindows(win_hwnd, cb, 0)
    return found  # 返回所有候选，调用方择优


def scroll_and_capture_contacts(win) -> list:
    """
    在通讯录列表区域逐屏截图。
    到底判断（三重保障，任一触发即停止）：
      1. Windows API 滚动条：nPos >= nMax（最可靠）
      2. 底部条带哈希：连续 4 次底部 1/5 区域像素完全相同
      3. 兜底上限：MAX_SHOTS 张
    """
    left, top, w, h = get_contacts_list_region(win)
    cx = left + w // 2
    cy = top  + h // 2

    # ── 尝试找列表子窗口句柄（用于滚动条检测）─────────────────────
    list_hwnds = find_contacts_list_hwnd(win['hwnd'])
    use_scrollbar_api = len(list_hwnds) > 0
    if use_scrollbar_api:
        print(f"  🪟 找到 {len(list_hwnds)} 个候选子窗口，启用滚动条 API 检测")
    else:
        print("  ⚠ 未找到子窗口，仅用图像检测到底")

    # ── 滚轮回顶 ────────────────────────────────────────────────────
    def scroll_to_top():
        pyautogui.moveTo(cx, cy)
        prev_h = None
        stable = 0
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
                    stable = 0
                    prev_h = cur_h
        time.sleep(0.5)

    print("⏫ 回到通讯录顶部...")
    pyautogui.click(cx, cy)
    time.sleep(0.4)
    scroll_to_top()
    print("  ✅ 已到顶部")

    # ── 校准每屏滚动格数（通过实测多格位移量计算）────────────────────
    print("🔧 校准滚动量...")
    pyautogui.moveTo(cx, cy)
    CALIB_STEPS = 5   # 校准时一次滚动 5 格，信号更明显
    shot_a = pyautogui.screenshot(region=(left, top, w, h))
    for _ in range(CALIB_STEPS):
        pyautogui.scroll(SCROLL_STEP)
        time.sleep(0.05)
    time.sleep(0.25)
    shot_b = pyautogui.screenshot(region=(left, top, w, h))
    arr_a = np.array(shot_a.convert('L'), dtype=np.int32)
    arr_b = np.array(shot_b.convert('L'), dtype=np.int32)
    best_offset, best_score = CALIB_STEPS, 1e9
    for off in range(1, min(200, h - 10)):
        score = np.mean(np.abs(arr_a[off:, :] - arr_b[:h - off, :]))
        if score < best_score:
            best_score, best_offset = score, off
    px_per_scroll_step = max(1, best_offset)  # 5 格对应的总像素位移
    px_per_one = px_per_scroll_step / CALIB_STEPS  # 单格像素
    # 每次截图后滚动约 70% 屏高（留 30% 重叠避免漏内容）
    steps_per_screen = max(8, int(h * 0.70 / max(1, px_per_one)))
    # 限制上限：单次不超过 60 格，防止滚太快跳过内容
    steps_per_screen = min(steps_per_screen, 60)
    print(f"  {CALIB_STEPS}格位移 ≈ {px_per_scroll_step}px，单格 ≈ {px_per_one:.1f}px，一屏滚 {steps_per_screen} 格")
    scroll_to_top()   # 校准时动了，再回顶

    # ── 逐屏截图 ────────────────────────────────────────────────────
    screenshots = []
    # 像素差值阈值：滚动后整图平均像素差 < 此值 → 认为页面没有移动（已到底）
    # 内容滚动时差值通常 > 10；到底后轻微渲染抖动差值通常 < 2
    PIXEL_DIFF_THRESHOLD  = 3.0
    BOTTOM_SAME_THRESHOLD = 2   # 连续 N 次像素差极小 → 确认到底

    print(f"📸 开始截图（最多 {MAX_SHOTS} 张）...")

    bottom_same_count = 0

    for i in range(MAX_SHOTS):
        time.sleep(0.25)

        # 滚动前截图
        shot_before = pyautogui.screenshot(region=(left, top, w, h))
        arr_before  = np.array(shot_before, dtype=np.float32)

        # 滚动一整屏
        pyautogui.moveTo(cx, cy)
        for _ in range(steps_per_screen):
            pyautogui.scroll(SCROLL_STEP)
            time.sleep(SCROLL_PAUSE)
        time.sleep(0.15)

        # 滚动后截图
        shot_after = pyautogui.screenshot(region=(left, top, w, h))
        arr_after  = np.array(shot_after, dtype=np.float32)

        # 保存滚动前的截图（内容页）
        screenshots.append(shot_before)

        # ─ 到底判断：像素差值法 ──────────────────────────────────────
        # 用整图像素差均值衡量页面是否真的移动了
        diff = np.mean(np.abs(arr_before - arr_after))

        if diff < PIXEL_DIFF_THRESHOLD:
            bottom_same_count += 1
            print(f"  第 {len(screenshots):03d} 张  [像素差={diff:.2f} 极小，未移动 {bottom_same_count}/{BOTTOM_SAME_THRESHOLD}]")
            if bottom_same_count >= BOTTOM_SAME_THRESHOLD:
                screenshots.append(shot_after)
                print(f"  ✅ [像素差值法] 连续{BOTTOM_SAME_THRESHOLD}次差值 < {PIXEL_DIFF_THRESHOLD}，已到底部，停止")
                break
        else:
            bottom_same_count = 0
            print(f"  第 {len(screenshots):03d} 张  [像素差={diff:.2f}]")

    else:
        print(f"  ⚠ 已达最大截图数 {MAX_SHOTS} 张，强制停止")

    print(f"  共截取 {len(screenshots)} 张")
    return screenshots



# ─────────────────────── OCR ────────────────────────────────────────

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        print("🔤 初始化 PaddleOCR...")
        import paddleocr
        _ocr_engine = paddleocr.PaddleOCR(
            use_angle_cls=False,
            lang='ch',
            use_gpu=False,
            show_log=False,
        )
        print("  ✅ PaddleOCR 初始化完成")
    return _ocr_engine


def ocr_contacts_page(pil_img: Image.Image) -> list:
    """
    OCR 一页通讯录截图，返回识别到的文字行列表。
    同一行（Y坐标相近）的多个文字块会合并成一条昵称。
    """
    ocr = get_ocr_engine()
    arr = np.array(pil_img)
    result = ocr.ocr(arr, cls=False)
    if not result or not result[0]:
        return []

    blocks = []
    for item in result[0]:
        box, (text, conf) = item
        if conf < 0.5:
            continue
        text = text.strip()
        if not text:
            continue
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        y_min, y_max = min(ys), max(ys)
        x_min = min(xs)
        y_center = (y_min + y_max) / 2
        row_h = y_max - y_min
        blocks.append({"text": text, "y": y_center, "x": x_min, "h": row_h, "conf": conf})

    if not blocks:
        return []

    # 按 Y 排序后，把 Y 差距 < 行高*0.6 的相邻块合并为同一行
    blocks.sort(key=lambda b: b["y"])
    merged = []
    group = [blocks[0]]
    for b in blocks[1:]:
        ref_h = max(g["h"] for g in group) if group else 20
        if abs(b["y"] - group[-1]["y"]) < ref_h * 0.6:
            group.append(b)
        else:
            # 同组按 X 排序后拼接文字
            group.sort(key=lambda g: g["x"])
            combined = "".join(g["text"] for g in group)
            avg_y = sum(g["y"] for g in group) / len(group)
            merged.append({"text": combined, "y": avg_y})
            group = [b]
    # 处理最后一组
    group.sort(key=lambda g: g["x"])
    combined = "".join(g["text"] for g in group)
    avg_y = sum(g["y"] for g in group) / len(group)
    merged.append({"text": combined, "y": avg_y})

    return merged



# ─────────────────────── 过滤昵称 ───────────────────────────────────

# 单字母/单数字索引行
ALPHA_ONLY = re.compile(r'^[A-Z#0-9]$')

# 明确的噪声词（通讯录UI文字、分类标题等）
NOISE_WORDS = {
    "新的朋友", "仅聊天", "公众号", "企业微信", "服务号", "订阅号",
    "群聊", "标签", "朋友圈", "设置", "收藏", "搜索",
    "通讯录管理", "通讯录管", "通讯录", "联系人", "企业微信联系人",
    "新朋友", "添加朋友", "雷达加朋友", "手机联系人",
    "变更", "预览", "选择文件以查看内容",
}

# 噪声前缀（OCR识别出来的UI前缀符号）
NOISE_PREFIXES = ("》", ">", "√", "✓", "V", "通讯录", "联系人", "<>")

# 包含这些关键词的行直接过滤
NOISE_CONTAINS = ["查看内容", "选择文件", "<>变更", "变更预览"]

def is_valid_nickname(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    # 单字母/数字索引
    if ALPHA_ONLY.match(t):
        return False
    # 去掉噪声前缀
    clean = t
    for p in NOISE_PREFIXES:
        if clean.startswith(p):
            clean = clean[len(p):].strip()
    if not clean:
        return False
    # 精确噪声词
    if clean in NOISE_WORDS or t in NOISE_WORDS:
        return False
    # 包含噪声关键词
    for kw in NOISE_CONTAINS:
        if kw in t:
            return False
    # 纯数字
    if re.match(r'^\d+$', t):
        return False
    # 纯标点/符号（无中文无字母无数字）
    if not re.search(r'[\w\u4e00-\u9fff]', t):
        return False
    # 太短且全是符号/字母片段（断行残留）
    if len(t) <= 2 and not re.search(r'[\u4e00-\u9fff]', t):
        return False
    return True



# ─────────────────────── 主流程 ─────────────────────────────────────

def main():
    print("=" * 55)
    print("  微信通讯录昵称抓取")
    print("=" * 55)

    hwnd, win = find_wechat_window()
    if not win:
        return

    # 切换到通讯录
    click_contacts_tab(win)

    # 截图
    screenshots = scroll_and_capture_contacts(win)

    # OCR 识别
    print("\n🔤 识别中...")
    all_lines = []
    for i, shot in enumerate(screenshots):
        print(f"  [{i+1:03d}/{len(screenshots)}]", end="  ", flush=True)
        lines = ocr_contacts_page(shot)
        print(f"{len(lines)} 行")
        all_lines.extend([l["text"] for l in lines])

    # 去重 + 过滤
    seen = set()
    nicknames = []
    for name in all_lines:
        name = name.strip()
        if name not in seen and is_valid_nickname(name):
            seen.add(name)
            nicknames.append(name)

    print(f"\n共识别到 {len(nicknames)} 个联系人昵称")

    # 输出结果 —— 只写纯昵称列表
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for name in nicknames:
            f.write(f"{name}\n")

    print(f"\n✅ 完成！")
    print(f"  输出 → {OUTPUT_FILE}")
    print(f"\n--- 前 30 个昵称预览 ---")
    for name in nicknames[:30]:
        print(f"  {name}")
    if len(nicknames) > 30:
        print(f"  ... 共 {len(nicknames)} 个")

    # 取消微信窗口置顶
    if win and win.get('hwnd'):
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        ctypes.windll.user32.SetWindowPos(win['hwnd'], HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


if __name__ == "__main__":
    main()
