# -*- coding: utf-8 -*-
"""测试 PaddleOCR predict() 返回数据结构"""
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import numpy as np
import cv2
from pathlib import Path
from paddleocr import PaddleOCR

# 用桌面截图测试
import pyautogui
print("截图中...")
shot = pyautogui.screenshot()
import cv2, numpy as np
img = cv2.cvtColor(np.array(shot.convert("RGB")), cv2.COLOR_RGB2BGR)
h, w = img.shape[:2]
img = cv2.resize(img, (w*3, h*3), interpolation=cv2.INTER_CUBIC)
# 只取中间一小块测试
img = img[300:900, 300:1200]

print("初始化 PaddleOCR (PP-OCRv4)...")
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    lang='ch',
    ocr_version='PP-OCRv4',
)
print("识别中...")
result = ocr.predict(img)
print(f"\n结果类型: {type(result)}")
print(f"结果长度: {len(result) if result else 0}")
if result:
    r0 = result[0]
    print(f"\nresult[0] 类型: {type(r0)}")
    if isinstance(r0, dict):
        print(f"result[0] 键: {list(r0.keys())}")
        for k, v in r0.items():
            print(f"  {k}: {type(v)} len={len(v) if hasattr(v,'__len__') else 'N/A'}")
            if hasattr(v, '__len__') and len(v) > 0:
                print(f"    [0]: {v[0]}")
    else:
        print(f"result[0]: {r0}")
