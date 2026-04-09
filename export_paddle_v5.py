# -*- coding: utf-8 -*-
"""
基于 PaddleOCR 重新识别已有截图，区分左右气泡（发言人）
输出 v5 版本 txt + html

逻辑：
  - 气泡中心 x < 图宽 * 0.45  → 左边 → 对方（AiLy）
  - 气泡中心 x > 图宽 * 0.55  → 右边 → 自己
  - 居中                       → 时间戳 / 系统通知
"""

import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import re
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from PIL import Image

# ===================== 配置 =====================
DESKTOP       = Path.home() / "Desktop"
CONTACT_NAME  = "AiLy 李15502540306"
SELF_NAME     = "我"          # 自己的显示名
OTHER_NAME    = "AiLy"        # 对方的显示名

# 气泡位置阈值（相对于图宽的比例）
LEFT_THRESH   = 0.45   # 中心 x < 45% → 对方
RIGHT_THRESH  = 0.55   # 中心 x > 55% → 自己

def find_latest_export_dir():
    dirs = sorted(
        [d for d in DESKTOP.iterdir()
         if d.is_dir() and d.name.startswith(f"微信导出_{CONTACT_NAME}")],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )
    return dirs[0] if dirs else None

EXPORT_DIR = find_latest_export_dir()
# ================================================


def preprocess_for_ocr(pil_img: Image.Image):
    """图像预处理：放大3x + 双边滤波，返回 OpenCV BGR 数组（彩色，PaddleOCR 自带灰度转换）"""
    img_cv = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img_cv.shape[:2]
    img_up = cv2.resize(img_cv, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
    img_denoised = cv2.bilateralFilter(img_up, d=9, sigmaColor=75, sigmaSpace=75)
    return img_denoised


def post_process_text(text: str) -> str:
    """后处理：修复时间戳空格，压缩中文字符间多余空格"""
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    text = re.sub(r'(\d)\s*[：:]\s*(\d)', r'\1:\2', text)
    text = re.sub(
        r'(?<=[\u4e00-\u9fff\uff00-\uffef])\s+(?=[\u4e00-\u9fff\uff00-\uffef\uff0c\u3002\uff01\uff1f\uff1a\uff1b\u3001])',
        '', text)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[，。！？：；、])', '', text)
    text = re.sub(r'(?<=[，。！？：；、])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[a-zA-Z0-9])', '', text)
    text = re.sub(r'(?<=[a-zA-Z0-9])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ── 噪声过滤 ──────────────────────────────────────────────────────────
NOISE_PATTERNS = [
    re.compile(r'^\d{1,2}二[A-Z0-9]\s*\d'),
    re.compile(r'^\.ocal\s*Ag'),
    re.compile(r'^\d\s*[,，]\s*\d{2}\s*[.．]\s*\d{2}'),
    re.compile(r'^[刂刁]\s*[官宫]'),
    re.compile(r'^[）)]\s*\d{1,2}\s*:\s*\d{2}'),
    re.compile(r'^[隼隹]\s*\d'),
    re.compile(r'^\d{4}$'),
    re.compile(r'^他人都'),
    re.compile(r'^亻回了\s*·\s*一消息'),
    re.compile(r'^你已添加了'),
    re.compile(r'已在其[他它].*设.*接听'),
    re.compile(r'^通话时长'),
    re.compile(r'(未接|已拒绝|邀请你.*通话|发起了.*通话)'),
    re.compile(r'^\[(图片|语音|视频|表情|文件|链接|位置|红包|转账)\]$'),
]

TIMESTAMP_PATTERNS = [
    re.compile(r'^星期[一二三四五六日]\s*\d{1,2}:\d{2}$'),
    re.compile(r'^星[一二三四五六日]\s*\d{1,2}:\d{2}$'),
    re.compile(r'^[阼昨今]\s*天\s*\d{1,2}:\d{2}$'),
    re.compile(r'^[阼昨今]天\s*\d{1,2}:\d{2}$'),
    re.compile(r'^星[．·\s]*期[一二三四五六日]\s*\d{1,2}:\d{2}$'),
    re.compile(r'^\d{1,2}:\d{2}$'),
    re.compile(r'^\d{4}-\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2}$'),
    re.compile(r'^[\u4e00-\u9fff]{1,4}\s*\d{1,2}:\d{2}$'),
]

def is_noise(text: str) -> bool:
    s = text.strip()
    if not s: return True
    chinese = re.findall(r'[\u4e00-\u9fff]', s)
    if len(s) <= 2 and not chinese: return True
    if re.match(r'^[^\u4e00-\u9fff\w]+$', s): return True
    if re.match(r'^\d{1,3}$', s): return True
    for pat in NOISE_PATTERNS:
        if pat.search(s): return True
    return False

def is_timestamp(text: str) -> bool:
    s = text.strip()
    for pat in TIMESTAMP_PATTERNS:
        if pat.match(s): return True
    return False


def classify_speaker(x_center: float, img_w: int) -> str:
    """根据气泡中心 x 坐标判断发言人"""
    ratio = x_center / img_w
    if ratio < LEFT_THRESH:
        return "other"   # 对方（左边）
    elif ratio > RIGHT_THRESH:
        return "self"    # 自己（右边）
    else:
        return "center"  # 居中（时间戳/系统通知）


def ocr_page(ocr_engine, pil_img: Image.Image, page_idx: int) -> list:
    """对单张截图做 OCR，返回结构化消息列表"""
    img_cv = preprocess_for_ocr(pil_img)
    img_w = img_cv.shape[1]

    result = ocr_engine.predict(img_cv)
    if not result or not result[0]:
        return []

    messages = []
    for line in result[0]:
        box, (text, conf) = line
        if conf < 0.5:   # 置信度过低直接跳过
            continue

        text = post_process_text(text)
        if not text or is_noise(text):
            continue

        # 计算气泡中心 x
        xs = [p[0] for p in box]
        x_center = sum(xs) / 4

        if is_timestamp(text):
            msg_type = "timestamp"
            speaker  = None
        else:
            msg_type = "message"
            speaker  = classify_speaker(x_center, img_w)
            if speaker == "center":
                # 居中但不是时间戳 → 可能是系统通知，作为时间戳行处理
                msg_type = "timestamp"
                speaker  = None

        # 记录 y 坐标用于排序
        ys = [p[1] for p in box]
        y_center = sum(ys) / 4

        messages.append({
            "text":    text,
            "type":    msg_type,
            "speaker": speaker,
            "page":    page_idx,
            "y":       y_center,
            "x":       x_center,
            "conf":    conf,
        })

    # 按 y 坐标排序（从上到下）
    messages.sort(key=lambda m: m["y"])
    return messages


def deduplicate(messages: list) -> list:
    """去重：相邻相同 + 高频固定行"""
    if not messages: return []

    # 相邻去重
    deduped, prev = [], ""
    for m in messages:
        if m["text"] != prev:
            deduped.append(m)
            prev = m["text"]

    # 高频去重（出现 ≥3 次视为 UI 固定元素）
    from collections import Counter
    counts = Counter(m["text"] for m in deduped)
    high = {t for t, c in counts.items() if c >= 3}
    if high:
        print(f"  [去重] 过滤 {len(high)} 个高频重复行（≥3次）:")
        for t in sorted(high, key=lambda x: -counts[x])[:6]:
            print(f"    - '{t[:50]}' (×{counts[t]})")
    return [m for m in deduped if m["text"] not in high]


# ── 保存 ──────────────────────────────────────────────────────────────

def save_txt(messages: list, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"微信聊天记录 - {CONTACT_NAME}\n")
        f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        for m in messages:
            if m["type"] == "timestamp":
                f.write(f"\n── {m['text']} ──\n\n")
            elif m["speaker"] == "self":
                f.write(f"[{SELF_NAME}] {m['text']}\n")
            else:
                f.write(f"[{OTHER_NAME}] {m['text']}\n")


def save_html(messages: list, path: Path):
    msg_count = sum(1 for m in messages if m["type"] == "message")
    rows = []
    for m in messages:
        text = (m["text"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        if m["type"] == "timestamp":
            rows.append(f'<div class="timestamp">{text}</div>')
        elif m["speaker"] == "self":
            rows.append(
                f'<div class="msg self">'
                f'<span class="name self-name">{SELF_NAME}</span>'
                f'<span class="bubble self-bubble">{text}</span>'
                f'</div>'
            )
        else:
            rows.append(
                f'<div class="msg other">'
                f'<span class="bubble other-bubble">{text}</span>'
                f'<span class="name other-name">{OTHER_NAME}</span>'
                f'</div>'
            )

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>聊天记录 - {CONTACT_NAME}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    background: #ededed;
    padding: 16px;
    min-height: 100vh;
}}
.chat-area {{
    max-width: 700px;
    margin: 0 auto;
    background: #f5f5f5;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    overflow: hidden;
    padding-bottom: 20px;
}}
.header {{
    background: #f5f5f5;
    border-bottom: 1px solid #d9d9d9;
    padding: 13px 20px;
    font-size: 16px;
    font-weight: 500;
    color: #191919;
    text-align: center;
}}
.meta-bar {{
    text-align: center;
    font-size: 12px;
    color: #aaa;
    padding: 8px 0 10px;
}}
/* 时间戳 */
.timestamp {{
    text-align: center;
    font-size: 12px;
    color: #b2b2b2;
    padding: 10px 0 4px;
    user-select: none;
}}
/* 消息行通用 */
.msg {{
    display: flex;
    align-items: flex-start;
    padding: 5px 16px;
    gap: 8px;
}}
/* 对方（左对齐） */
.msg.other {{
    flex-direction: row;
    justify-content: flex-start;
}}
/* 自己（右对齐） */
.msg.self {{
    flex-direction: row-reverse;
    justify-content: flex-start;
}}
/* 姓名标签 */
.name {{
    font-size: 12px;
    color: #999;
    white-space: nowrap;
    padding-top: 6px;
    min-width: 24px;
}}
.self-name {{ text-align: right; }}
.other-name {{ text-align: left; }}
/* 气泡 */
.bubble {{
    display: inline-block;
    font-size: 14px;
    line-height: 1.7;
    padding: 8px 12px;
    max-width: 68%;
    word-break: break-all;
    white-space: pre-wrap;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
}}
/* 对方气泡：白色，左圆角小 */
.other-bubble {{
    background: #ffffff;
    color: #191919;
    border-radius: 4px 12px 12px 12px;
}}
/* 自己气泡：绿色，右圆角小 */
.self-bubble {{
    background: #95ec69;
    color: #191919;
    border-radius: 12px 4px 12px 12px;
}}
</style>
</head>
<body>
<div class="chat-area">
  <div class="header">💬 {CONTACT_NAME}</div>
  <div class="meta-bar">共 {msg_count} 条消息 · 导出于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  {''.join(rows)}
</div>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    if not EXPORT_DIR:
        print(f"❌ 未找到导出目录")
        return

    print(f"📂 导出目录: {EXPORT_DIR}")
    raw_dir = EXPORT_DIR / "raw_screenshots"
    if not raw_dir.exists():
        print(f"❌ 截图目录不存在: {raw_dir}")
        return

    png_files = sorted(raw_dir.glob("page_*.png"))
    print(f"📸 找到 {len(png_files)} 张截图\n")

    # 初始化 PaddleOCR
    print("🔧 初始化 PaddleOCR...")
    from paddleocr import PaddleOCR
    # 尝试禁用 oneDNN 并使用 CPU 推理来避免兼容性问题
    import os
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = '1'
    os.environ['PADDLE_DISABLE_ONEDNN'] = '1'
    
    ocr = PaddleOCR(
        lang='ch'
    )
    print("✅ PaddleOCR 就绪\n")

    all_messages = []
    for i, png_path in enumerate(png_files):
        print(f"  [{i+1:02d}/{len(png_files)}] {png_path.name}", end="  ")
        orig = Image.open(png_path)
        msgs = ocr_page(ocr, orig, i)
        n_msg = sum(1 for m in msgs if m["type"] == "message")
        n_ts  = sum(1 for m in msgs if m["type"] == "timestamp")
        print(f"消息 {n_msg} 条 / 时间戳 {n_ts} 条")
        all_messages.extend(msgs)

    print(f"\n共 {len(all_messages)} 行，去重中...")
    all_messages = deduplicate(all_messages)
    print(f"去重后 {len(all_messages)} 行")

    txt_path  = EXPORT_DIR / f"{CONTACT_NAME}_聊天记录_v5.txt"
    html_path = EXPORT_DIR / f"{CONTACT_NAME}_聊天记录_v5.html"
    save_txt(all_messages, txt_path)
    save_html(all_messages, html_path)

    print(f"\n✅ 完成！")
    print(f"  TXT  → {txt_path}")
    print(f"  HTML → {html_path}")

    # 预览前30行
    print("\n--- TXT 预览（前30行）---")
    with open(txt_path, encoding="utf-8") as f:
        for j, line in enumerate(f):
            if j >= 33: break
            print(f"  {line}", end="")

    os.startfile(EXPORT_DIR)


if __name__ == "__main__":
    main()
