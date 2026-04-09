# -*- coding: utf-8 -*-
"""识别指定图片"""
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import asyncio
from PIL import Image
import winsdk.windows.media.ocr as winrt_ocr
import winsdk.windows.globalization as globalization
import winsdk.windows.graphics.imaging as imaging
import winsdk.windows.storage.streams as streams
import io

async def ocr_image(path: str):
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
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
    
    result = await engine.recognize_async(soft_bmp)
    
    print(f"识别到 {len(result.lines)} 行文字：\n")
    for line in result.lines:
        # 获取文字块的边界框坐标
        rect = line.bounding_rect
        x = rect.x + rect.width / 2  # 中心x坐标
        print(f"[{x:.0f}] {line.text}")

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else input("图片路径: ").strip()
    asyncio.run(ocr_image(path))
