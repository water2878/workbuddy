import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
import warnings
warnings.filterwarnings('ignore')

from paddleocr import PaddleOCR
import glob, numpy as np
from PIL import Image

# 2.x 旧版 API：ocr(img, cls=False)
ocr = PaddleOCR(use_angle_cls=False, lang='ch', use_gpu=False, show_log=False)

shots = glob.glob(r'C:/Users/Lenovo/Desktop/微信导出_*/raw_screenshots/page_0001.png')
if not shots:
    print("没找到截图"); exit()

img_path = shots[0]
print("测试图:", img_path)
img = np.array(Image.open(img_path))

result = ocr.ocr(img, cls=False)
print("result type:", type(result))
if result and result[0]:
    print(f"识别到 {len(result[0])} 行:")
    for item in result[0][:10]:
        box, (text, conf) = item
        xs = [p[0] for p in box]
        print(f"  [{conf:.2f}] x={int(sum(xs)/4):4d}  {text}")
