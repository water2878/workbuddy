# -*- coding: utf-8 -*-
"""测试 PaddleOCR 对微信截图的识别效果 + 坐标"""
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from paddleocr import PaddleOCR
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

SCREENSHOT = Path(r"C:\Users\Lenovo\Desktop\微信导出_AiLy 李15502540306_20260316_125450\raw_screenshots\page_0005.png")

def preprocess(pil_img):
    img_cv = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img_cv.shape[:2]
    img_up = cv2.resize(img_cv, (w*3, h*3), interpolation=cv2.INTER_CUBIC)
    img_denoised = cv2.bilateralFilter(img_up, 9, 75, 75)
    return img_denoised  # 返回彩色图给 PaddleOCR（它自己做灰度）

print("初始化 PaddleOCR (lang=ch)...")
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='ch')

img = Image.open(SCREENSHOT)
img_cv = preprocess(img)
img_w = img_cv.shape[1]
mid = img_w // 2
print(f"图像宽: {img_w}px  中线: {mid}px\n")

print("识别中...")
result = ocr.ocr(img_cv, cls=False)

if result and result[0]:
    print(f"{'文字':<35} {'x左':>6} {'中心x':>6} {'置信度':>6}  {'发言人'}")
    print("-" * 75)
    for line in result[0]:
        box, (text, conf) = line
        # box = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        xs = [p[0] for p in box]
        x_left = min(xs)
        x_center = sum(xs) / 4
        if x_center < mid * 0.6:
            speaker = "← 对方(AiLy)"
        elif x_center > mid * 0.8:
            speaker = "→ 自己"
        else:
            speaker = "─ 居中(时间戳?)"
        print(f"{text[:33]:<35} {x_left:>6.0f} {x_center:>6.0f} {conf:>6.3f}  {speaker}")
