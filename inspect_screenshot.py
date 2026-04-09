# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from PIL import Image
from pathlib import Path

raw_dir = Path.home() / "Desktop" / "微信导出_AiLy 李15502540306_20260316_125450" / "raw_screenshots"
files = sorted(raw_dir.glob("page_*.png"))

for f in files[:3]:
    img = Image.open(f)
    w, h = img.size
    print(f"{f.name}: {w} x {h}")
    # 采样各高度段的平均像素，帮助判断顶底边界
    import numpy as np
    arr = np.array(img)
    for y_pct in [0, 3, 5, 7, 10, 85, 90, 93, 96, 100]:
        y = min(int(h * y_pct / 100), h-1)
        row_mean = arr[y].mean()
        print(f"  y={y:4d} ({y_pct:3d}%)  avg_brightness={row_mean:.1f}")
    print()
