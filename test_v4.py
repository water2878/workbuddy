# -*- coding: utf-8 -*-
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

print("导入PaddleOCR...", flush=True)
from paddleocr import PaddleOCR
print("初始化 PP-OCRv4...", flush=True)
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    lang='ch',
    ocr_version='PP-OCRv4',
)
print("初始化完成！测试识别...", flush=True)

import numpy as np
import pyautogui
shot = pyautogui.screenshot()
import cv2
img = cv2.cvtColor(np.array(shot.convert("RGB")), cv2.COLOR_RGB2BGR)
img = img[300:600, 300:900]  # 小块测试

print("调用 predict...", flush=True)
for r in ocr.predict(img):
    texts = r.get("rec_texts", [])
    print(f"识别到 {len(texts)} 行文字")
    for t in texts[:5]:
        print(f"  '{t}'")
print("测试完成！")
