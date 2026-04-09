# -*- coding: utf-8 -*-
"""
对已有截图重新进行预处理 + OCR，解决乱码问题

预处理流程：
  1. 裁切掉截图顶部/底部的非聊天区域
  2. 用 OpenCV 放大 3x（INTER_CUBIC）
  3. 双边滤波去噪（保边缘）
  4. 转灰度
  5. 自适应阈值二值化（增强对比度）
  6. 再用 PIL.ImageEnhance 增强对比度
  7. 送给 WinRT OCR（zh-Hans）

用法：
    python reocr_with_preprocess.py
"""

import sys
import io as _pyio
sys.stdout = _pyio.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _pyio.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import re
import asyncio
import glob
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

# ===================== 配置 =====================
# 最近一次导出目录（自动找最新的）
DESKTOP = Path.home() / "Desktop"
CONTACT_NAME = "AiLy 李15502540306"

def find_latest_export_dir():
    dirs = sorted(
        [d for d in DESKTOP.iterdir() if d.is_dir() and d.name.startswith(f"微信导出_{CONTACT_NAME}")],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )
    return dirs[0] if dirs else None

EXPORT_DIR = find_latest_export_dir()
# ================================================


def preprocess_for_ocr(pil_img: Image.Image) -> Image.Image:
    """
    对截图做多步预处理，提升 OCR 准确率：
    1. 转为 OpenCV BGR
    2. 放大 3x（双三次插值）
    3. 双边滤波去噪
    4. 转灰度
    5. 自适应高斯阈值二值化
    6. 再轻微锐化
    """
    # PIL → OpenCV
    img_cv = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    
    # 1. 放大 3x（双三次插值，适合文字）
    h, w = img_cv.shape[:2]
    scale = 3
    img_up = cv2.resize(img_cv, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    
    # 2. 双边滤波（去噪同时保留文字边缘）
    img_denoised = cv2.bilateralFilter(img_up, d=9, sigmaColor=75, sigmaSpace=75)
    
    # 3. 转灰度
    img_gray = cv2.cvtColor(img_denoised, cv2.COLOR_BGR2GRAY)
    
    # 4. 自适应高斯二值化（blockSize=31, C=10 适合微信聊天文字大小）
    img_bin = cv2.adaptiveThreshold(
        img_gray,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=10
    )
    
    # 5. 轻微膨胀让细字变粗（提升识别率）
    kernel = np.ones((2, 2), np.uint8)
    img_bin = cv2.dilate(img_bin, kernel, iterations=1)
    
    # 6. OpenCV → PIL，再增强对比度
    pil_result = Image.fromarray(img_bin).convert("RGB")
    pil_result = ImageEnhance.Sharpness(pil_result).enhance(2.0)
    
    return pil_result


def ocr_winrt(pil_img: Image.Image) -> list:
    """WinRT OCR，返回文字行列表"""
    import winsdk.windows.media.ocr as winrt_ocr
    import winsdk.windows.globalization as globalization
    import winsdk.windows.graphics.imaging as imaging
    import winsdk.windows.storage.streams as streams
    import io as _io

    async def do_ocr():
        buf = _io.BytesIO()
        pil_img.save(buf, format="PNG")
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
        lines = []
        for line in result.lines:
            # WinRT 会在每个字之间加空格，需要后处理
            text = line.text.strip()
            if text:
                lines.append(text)
        return lines

    try:
        return asyncio.run(do_ocr())
    except Exception as e:
        print(f"  ⚠️ OCR 出错: {e}")
        return []


def post_process_line(line: str) -> str:
    """
    后处理 WinRT OCR 的输出：
    1. 去掉中文字符之间的空格
    2. 修复时间戳中数字和冒号间的空格（如 "1 1 ： 3 9" → "11:39"）
    """
    # 修复时间戳：数字-空格-冒号-空格-数字 → 去掉空格
    # 如 "1 1 ： 3 9" → "11:39"，"昨天1 6 ： 1 8" → "昨天16:18"
    line = re.sub(r'(\d)\s+(\d)', r'\1\2', line)         # "1 6" → "16"
    line = re.sub(r'(\d)\s*[：:]\s*(\d)', r'\1:\2', line) # "11 ： 39" → "11:39"
    
    # 去掉中文字符之间的空格
    result = re.sub(
        r'(?<=[\u4e00-\u9fff\uff00-\uffef])\s+(?=[\u4e00-\u9fff\uff00-\uffef\uff0c\u3002\uff01\uff1f\uff1a\uff1b\u3001\u201c\u201d\u2018\u2019\uff08\uff09\u3010\u3011\u300a\u300b])',
        '', line
    )
    # 去掉中文字符和标点之间的空格
    result = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\uff0c\u3002\uff01\uff1f\uff1a\uff1b\u3001，。！？：；、])', '', result)
    result = re.sub(r'(?<=[\uff0c\u3002\uff01\uff1f\uff1a\uff1b\u3001，。！？：；、])\s+(?=[\u4e00-\u9fff])', '', result)
    # 去掉中文和英文之间多余空格
    result = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[a-zA-Z0-9])', '', result)
    result = re.sub(r'(?<=[a-zA-Z0-9])\s+(?=[\u4e00-\u9fff])', '', result)
    # 压缩多余空格
    result = re.sub(r' {2,}', ' ', result)
    return result.strip()


# ── 噪声过滤规则（状态栏 / UI 控件 / 时间戳 / 系统通知）──────────────────
#
# 分三类：
#   A. 状态栏/窗口 UI（来自截图顶部）
#   B. 时间戳行（居中灰色小字，如"星期五 14:30"）
#   C. 系统通知（"你已添加了..."、"已在其它设备接听" 等）
#
NOISE_PATTERNS = [
    # ── A. 状态栏 / 窗口 UI ────────────────────────────────────────
    re.compile(r'^\d{1,2}二[A-Z0-9]\s*\d'),            # "12二52" 信号格
    re.compile(r'^\.ocal\s*Ag'),                         # ".ocal Ag.." WLAN
    re.compile(r'^\d\s*[,，]\s*\d{2}\s*[.．]\s*\d{2}'), # "0，12．03" 状态栏时间
    re.compile(r'^[刂刁]\s*[官宫]'),                     # "刂官" 图标
    re.compile(r'^[）)]\s*\d{1,2}\s*:\s*\d{2}'),        # "）11:17" 括号时间
    re.compile(r'^[隼隹]\s*\d'),                          # "隼0" 图标
    re.compile(r'^\d{4}$'),                              # 纯4位数（信号/电量）
    re.compile(r'^他人都'),                               # 状态栏通讯录
    re.compile(r'^亻回了\s*·\s*一消息'),                  # UI 元素

    # ── B. 时间戳行已移至 is_timestamp_line() 单独处理，此处不再过滤 ──

    # ── C. 系统通知（单行、内容固定）──────────────────────────────
    # "你已添加了AiLy李15502540306，现在可以开始聊天了。"
    re.compile(r'^你已添加了'),
    # "已在其它设备接听" / "^ 已在其它设接听"
    re.compile(r'已在其[他它].*设.*接听'),
    # "通话时长12:43"
    re.compile(r'^通话时长'),
    # 语音/视频通话被拒绝/未接
    re.compile(r'(未接|已拒绝|邀请你.*通话|发起了.*通话)'),
    # "[图片]" "[语音]" "[视频]" 等占位符
    re.compile(r'^\[(图片|语音|视频|表情|文件|链接|位置|红包|转账)\]$'),
]


def is_noise_line(line: str) -> bool:
    """
    判断是否为噪声行（状态栏、时间戳、系统通知）。
    返回 True 表示应该过滤掉，False 表示是真实消息内容。
    """
    stripped = line.strip()

    # 空行
    if not stripped:
        return True

    # 太短且无中文（纯符号/单字母/单数字）
    chinese = re.findall(r'[\u4e00-\u9fff]', stripped)
    if len(stripped) <= 2 and not chinese:
        return True

    # 全是特殊符号（无中文无字母数字）
    if re.match(r'^[^\u4e00-\u9fff\w]+$', stripped):
        return True

    # 纯短数字（如 "0" "42"），排除有实际含义的数字
    if re.match(r'^\d{1,3}$', stripped):
        return True

    # 匹配噪声规则
    for pat in NOISE_PATTERNS:
        if pat.search(stripped):
            return True

    return False


# 时间戳行识别规则
TIMESTAMP_PATTERNS = [
    re.compile(r'^星期[一二三四五六日]\s*\d{1,2}:\d{2}$'),          # "星期五14:30"
    re.compile(r'^星[一二三四五六日]\s*\d{1,2}:\d{2}$'),            # "星五14:30"（误识别）
    re.compile(r'^[阼昨今]\s*天\s*\d{1,2}:\d{2}$'),                 # "昨天09:47"
    re.compile(r'^[阼昨今]天\s*\d{1,2}:\d{2}$'),                    # 紧凑格式
    re.compile(r'^星[．·\s]*期[一二三四五六日]\s*\d{1,2}:\d{2}$'),  # 带顿号误识别
    re.compile(r'^\d{1,2}:\d{2}$'),                                  # 纯时间 "09:47"
    re.compile(r'^\d{4}-\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2}$'),        # "2026-03-14 09:47"
    re.compile(r'^[\u4e00-\u9fff]{1,4}\s*\d{1,2}:\d{2}$'),          # "昨天16:18" 等
]


def is_timestamp_line(line: str) -> bool:
    """判断是否为时间戳行（应展示为居中灰色，而非消息气泡）"""
    stripped = line.strip()
    for pat in TIMESTAMP_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def parse_messages(lines: list, page_idx: int) -> list:
    """从 OCR 行中解析消息，区分时间戳行和消息行"""
    messages = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if is_timestamp_line(line):
            messages.append({"text": line, "page": page_idx, "type": "timestamp"})
        else:
            messages.append({"text": line, "page": page_idx, "type": "message"})
    return messages


def deduplicate(messages: list) -> list:
    """跨页去重（相邻相同文本 + 全局重复行）"""
    if not messages:
        return []
    
    # 第1步：去掉相邻重复
    deduped = []
    prev = ""
    for msg in messages:
        if msg["text"] != prev:
            deduped.append(msg)
            prev = msg["text"]
    
    # 第2步：检测并去掉大量重复的"固定块"
    # 统计每行出现次数，超过2次的疑似是截图顶部固定UI元素或跨页重复内容
    from collections import Counter
    text_counts = Counter(m["text"] for m in deduped)
    high_freq = {t for t, c in text_counts.items() if c >= 3}
    
    if high_freq:
        print(f"  [去重] 发现 {len(high_freq)} 个高频重复行，将过滤（出现≥3次）:")
        for t in sorted(high_freq, key=lambda x: -text_counts[x])[:8]:
            print(f"    - '{t[:50]}' (×{text_counts[t]})")
        deduped = [m for m in deduped if m["text"] not in high_freq]
    
    return deduped


def save_txt(messages: list, contact: str, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"微信聊天记录 - {contact}\n")
        f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        for msg in messages:
            if msg.get("type") == "timestamp":
                # 时间戳单独一行，前后各空一行，居中对齐
                f.write(f"\n── {msg['text']} ──\n\n")
            else:
                f.write(msg["text"] + "\n")


def save_html(messages: list, contact: str, path: Path):
    rows = []
    msg_count = sum(1 for m in messages if m.get("type") != "timestamp")
    for msg in messages:
        text = msg["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if msg.get("type") == "timestamp":
            rows.append(f'<div class="timestamp">{text}</div>')
        else:
            rows.append(f'<div class="msg"><span class="bubble">{text}</span></div>')

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>聊天记录 - {contact}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    background: #ededed;
    padding: 16px;
    min-height: 100vh;
}}
.header {{
    background: #f5f5f5;
    border-bottom: 1px solid #d9d9d9;
    padding: 12px 20px;
    font-size: 16px;
    font-weight: 500;
    color: #191919;
    text-align: center;
    letter-spacing: 0.5px;
    margin-bottom: 0;
    border-radius: 8px 8px 0 0;
}}
.chat-area {{
    max-width: 680px;
    margin: 0 auto;
    background: #f5f5f5;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    padding-bottom: 16px;
}}
.meta-bar {{
    text-align: center;
    font-size: 12px;
    color: #aaa;
    padding: 8px 0 12px;
}}
/* 时间戳：居中灰色小字，微信原生风格 */
.timestamp {{
    text-align: center;
    font-size: 12px;
    color: #b2b2b2;
    padding: 10px 0 6px;
    user-select: none;
}}
/* 消息气泡 */
.msg {{
    padding: 4px 16px;
    display: flex;
    justify-content: flex-start;
}}
.bubble {{
    display: inline-block;
    background: #ffffff;
    color: #191919;
    font-size: 14px;
    line-height: 1.7;
    padding: 8px 12px;
    border-radius: 4px 12px 12px 12px;
    max-width: 75%;
    word-break: break-all;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    white-space: pre-wrap;
}}
</style>
</head>
<body>
<div class="chat-area">
  <div class="header">💬 {contact}</div>
  <div class="meta-bar">共 {msg_count} 条消息 · 导出于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  {''.join(rows)}
</div>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    if not EXPORT_DIR:
        print(f"❌ 未找到导出目录: 微信导出_{CONTACT_NAME}_*")
        return

    print(f"📂 导出目录: {EXPORT_DIR}")
    
    raw_dir = EXPORT_DIR / "raw_screenshots"
    if not raw_dir.exists():
        print(f"❌ 截图目录不存在: {raw_dir}")
        return

    png_files = sorted(raw_dir.glob("page_*.png"))
    print(f"📸 找到 {len(png_files)} 张截图\n")

    if not png_files:
        print("❌ 没有找到截图文件")
        return

    # 保存预处理后的截图，方便检查效果
    preproc_dir = EXPORT_DIR / "preprocessed"
    preproc_dir.mkdir(exist_ok=True)

    all_messages = []
    
    for i, png_path in enumerate(png_files):
        print(f"  [{i+1:02d}/{len(png_files)}] 处理: {png_path.name}", end="  ")
        
        # 加载截图
        orig = Image.open(png_path)
        
        # 图像预处理
        processed = preprocess_for_ocr(orig)
        
        # 保存预处理结果（供检查）
        processed.save(preproc_dir / png_path.name)
        
        # OCR
        raw_lines = ocr_winrt(processed)
        
        # 后处理
        lines = [post_process_line(l) for l in raw_lines]
        lines = [l for l in lines if l and not is_noise_line(l)]
        
        print(f"识别 {len(lines)} 行")
        
        msgs = parse_messages(lines, i)
        all_messages.extend(msgs)

    print(f"\n共识别 {len(all_messages)} 行文字，去重中...")
    all_messages = deduplicate(all_messages)
    print(f"去重后 {len(all_messages)} 行")

    # 保存结果
    txt_path  = EXPORT_DIR / f"{CONTACT_NAME}_聊天记录_v4.txt"
    html_path = EXPORT_DIR / f"{CONTACT_NAME}_聊天记录_v4.html"
    
    save_txt(all_messages, CONTACT_NAME, txt_path)
    save_html(all_messages, CONTACT_NAME, html_path)
    
    print(f"\n✅ 完成！")
    print(f"  TXT  → {txt_path}")
    print(f"  HTML → {html_path}")
    print(f"  预处理截图 → {preproc_dir}")
    
    # 预览 TXT 前30行
    print("\n--- TXT 预览（前30行）---")
    with open(txt_path, encoding="utf-8") as f:
        for j, line in enumerate(f):
            if j >= 33:
                break
            print(f"  {line}", end="")
    
    # 打开目录
    os.startfile(EXPORT_DIR)


if __name__ == "__main__":
    main()
