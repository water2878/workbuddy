import asyncio
import winsdk.windows.media.ocr as winrt_ocr
import winsdk.windows.globalization as globalization
import winsdk.windows.graphics.imaging as imaging
import winsdk.windows.storage.streams as streams
from PIL import Image, ImageDraw
import io
import pyautogui

async def main():
    # 直接截一张真实屏幕截图来测试
    shot = pyautogui.screenshot()
    shot = shot.crop((0, 0, 600, 400))
    buf = io.BytesIO()
    shot.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    img_bytes = buf.read()

    dw = streams.DataWriter()
    dw.write_bytes(img_bytes)
    stream = streams.InMemoryRandomAccessStream()
    await stream.write_async(dw.detach_buffer())
    stream.seek(0)

    decoder = await imaging.BitmapDecoder.create_async(stream)
    soft_bmp = await decoder.get_software_bitmap_async()

    engine = winrt_ocr.OcrEngine.try_create_from_language(
        globalization.Language("zh-Hans"))
    if engine is None:
        engine = winrt_ocr.OcrEngine.try_create_from_user_profile_languages()

    result = await engine.recognize_async(soft_bmp)
    print(f"识别到 {len(result.lines)} 行")
    for line in result.lines:
        print("--- OcrLine attrs:", [a for a in dir(line) if not a.startswith('_')])
        print("    text:", line.text)
        if hasattr(line, 'words') and line.words:
            w = line.words[0]
            print("    OcrWord attrs:", [a for a in dir(w) if not a.startswith('_')])
        break

asyncio.run(main())
