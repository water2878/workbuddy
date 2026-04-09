# -*- coding: utf-8 -*-
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import cv2, numpy as np
from PIL import Image

print("加载图片...", flush=True)
img = Image.open(r"C:\Users\Lenovo\Pictures\ocr_test.png")

print(f"图片尺寸: {img.size}", flush=True)

# WinRT OCR
import asyncio
import winsdk.windows.media.ocr as winrt_ocr
import winsdk.windows.globalization as globalization
import winsdk.windows.graphics.imaging as imaging
import winsdk.windows.storage.streams as streams
import io as _io2

async def do_ocr(pil_img):
    buf = _io2.BytesIO()
    pil_img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    img_bytes = buf.read()
    dw = streams.DataWriter()
    dw.write_bytes(img_bytes)
    stream = streams.InMemoryRandomAccessStream()
    await stream.write_async(dw.detach_buffer())
    stream.seek(0)
    decoder = await imaging.BitmapDecoder.create_async(stream)
    soft_bmp = await decoder.get_software_bitmap_async()
    engine = winrt_ocr.OcrEngine.try_create_from_language(globalization.Language("zh-Hans"))
    if not engine:
        engine = winrt_ocr.OcrEngine.try_create_from_user_profile_languages()
    result = await engine.recognize_async(soft_bmp)
    return result

result = asyncio.run(do_ocr(img))
img_w = img.width

print(f"\n共识别 {len(result.lines)} 行：\n")
for line in result.lines:
    r = line.bounding_rect
    cx = r.x + r.width / 2
    side = "左(对方)" if cx/img_w < 0.45 else ("右(自己)" if cx/img_w > 0.55 else "中(时间/系统)")
    print(f"  [{side:8s}] {line.text}")
