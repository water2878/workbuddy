# -*- coding: utf-8 -*-
"""
测试 PaddleOCR 基本功能
"""

import os
import cv2
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

# 禁用 oneDNN 避免兼容性问题
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['PADDLE_DISABLE_ONEDNN'] = '1'

print("初始化 PaddleOCR...")
try:
    ocr = PaddleOCR(lang='ch')
    print("PaddleOCR 初始化成功")
    
    # 测试一张简单的图片
    print("测试 OCR 功能...")
    
    # 创建一个简单的测试图片
    test_image = np.zeros((100, 400, 3), dtype=np.uint8)
    test_image[:] = 255  # 白色背景
    
    # 添加一些文字
    cv2.putText(test_image, "你好，这是测试文字", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    
    # 保存测试图片
    test_path = "test_image.png"
    cv2.imwrite(test_path, test_image)
    print(f"创建测试图片: {test_path}")
    
    # 运行 OCR
    result = ocr.predict(test_path)
    print(f"OCR 结果: {result}")
    
    # 清理测试文件
    if os.path.exists(test_path):
        os.remove(test_path)
    
    print("测试成功完成！")
    
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()