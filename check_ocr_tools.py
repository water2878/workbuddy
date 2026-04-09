# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

results = {}

# PIL
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    results['PIL'] = 'ok'
except Exception as e:
    results['PIL'] = str(e)

# pytesseract
try:
    import pytesseract
    v = pytesseract.get_tesseract_version()
    results['pytesseract'] = f'ok, version={v}'
except Exception as e:
    results['pytesseract'] = str(e)

# winsdk / winrt
try:
    import winsdk.windows.media.ocr as winrt_ocr
    import winsdk.windows.globalization as globalization
    engine = winrt_ocr.OcrEngine.try_create_from_language(globalization.Language("zh-Hans"))
    results['winrt'] = f'ok, engine={engine is not None}'
except Exception as e:
    results['winrt'] = str(e)

# opencv
try:
    import cv2
    results['opencv'] = f'ok, version={cv2.__version__}'
except Exception as e:
    results['opencv'] = str(e)

# paddleocr
try:
    import paddleocr
    results['paddleocr'] = 'ok'
except Exception as e:
    results['paddleocr'] = str(e)

for k, v in results.items():
    print(f"  {k}: {v}")
