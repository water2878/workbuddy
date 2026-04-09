# -*- coding: utf-8 -*-
"""测试 WinRT OCR 是否能返回每行的 x 坐标（用于判断左右气泡）"""
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import asyncio
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

# 用一张已有的截图测试
SCREENSHOT = Path(r"C:\Users\Lenovo\Desktop\微信导出_AiLy 李15502540306_20260316_125450\raw_screenshots\page_0005.png")

async def do_ocr(pil_img):
    import winsdk.windows.media.ocr as winrt_ocr
    import winsdk.windows.globalization as globalization
    import winsdk.windows.graphics.imaging as imaging
    import winsdk.windows.storage.streams as streams
    import io as _io2

    buf = _io2.BytesIO()
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
    result = await engine.recognize_async(soft_bmp)

    img_w = pil_img.width
    print(f"图像宽度: {img_w}px，中线: {img_w//2}px")
    print(f"{'文字':<30} {'x':>6} {'y':>6} {'w':>6} {'left/right'}")
    print("-" * 65)

    for line in result.lines:
        text = line.text.strip()
        if not text:
            continue
        # 获取该行所有 word 的 bounding rect
        words = line.words
        if words and len(words) > 0:
            try:
                # 取第一个 word 的 x 坐标
                first_word = words[0]
                rect = first_word.bounding_rect
                x, y, w, h = rect.x, rect.y, rect.width, rect.height
                side = "← 左(对方)" if x < img_w * 0.4 else "→ 右(自己)" if x > img_w * 0.5 else "中(时间戳)"
                print(f"{text[:28]:<30} {x:>6.0f} {y:>6.0f} {w:>6.0f}  {side}")
            except Exception as e:
                print(f"{text[:28]:<30}  (无坐标: {e})")
        else:
            print(f"{text[:28]:<30}  (无words)")

def main():
    img = Image.open(SCREENSHOT)
    # 放大3x（和正式脚本一样）
    img_cv = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img_cv.shape[:2]
    img_up = cv2.resize(img_cv, (w*3, h*3), interpolation=cv2.INTER_CUBIC)
    img_denoised = cv2.bilateralFilter(img_up, 9, 75, 75)
    img_gray = cv2.cvtColor(img_denoised, cv2.COLOR_BGR2GRAY)
    img_bin = cv2.adaptiveThreshold(img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
    pil_img = Image.fromarray(img_bin).convert("RGB")

    asyncio.run(do_ocr(pil_img))

if __name__ == "__main__":
    main()
