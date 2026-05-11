# -*- coding: utf-8 -*-
"""产品知识库模块 - 合同审批服务器专用"""

import os
import re
from typing import Dict, Optional

# 产品知识库目录（相对于当前文件）
PRODUCT_KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "products")

# 产品标准价格表（单位：元）
STANDARD_PRICES = {
    'T412': 680,
    'T423': 980,
    'T435': 1180,
    'T522': 780,
    'T523': 880,
    'T524': 980,
    'T526': 1080,
    'T526B': 1180,
    'T545': 1280,
    'T621': 880,
    'F4200': 680,
    'F4206': 720,
    'F4212': 580,
    'F435': 1080,
    'F4404': 780,
    'F5S': 880,
    'T6201': 780,
    'T724': 1480,
    'T727': 1680,
    'T728': 1880,
    'T729': 2080,
    'TA1': 480,
    '4410C': 580,
}


def extract_product_params(model: str) -> Dict[str, str]:
    """从产品知识库提取指定型号的参数"""
    kb_file = _find_kb_file(model)
    if not kb_file:
        return {}

    with open(kb_file, 'r', encoding='utf-8') as f:
        content = f.read()

    params = {}

    color_match = re.search(r'桌架颜色.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if color_match:
        params['color'] = color_match.group(1).strip()

    packing_match = re.search(r'包装规格.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    packing = packing_match.group(1).strip() if packing_match else ''
    if packing:
        vol_match = re.search(r'(\d+)\*(\d+)\*(\d+)\s*mm', packing)
        if vol_match:
            l, w, h = vol_match.groups()
            volume_m3 = (int(l) * int(w) * int(h)) / 1_000_000_000
            params['volume'] = f"{l}×{w}×{h}mm ({volume_m3:.4f}m³)"

        weight_match = re.search(r'(\d+)\s*KG', packing)
        if weight_match:
            params['weight'] = f"{weight_match.group(1)}KG"

    frame_match = re.search(r'横梁伸缩范围.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if frame_match:
        params['frame_size'] = frame_match.group(1).strip()

    lift_match = re.search(r'升降高度范围.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if lift_match:
        params['lift_range'] = lift_match.group(1).strip()

    desc_match = re.search(r'产品概述.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if desc_match:
        params['description'] = desc_match.group(1).strip()

    return {k: v for k, v in params.items() if v}


def get_standard_price(model: str) -> float:
    """获取产品标准价格"""
    return STANDARD_PRICES.get(model.upper(), 0)


# 面板型号（通用）
PANEL_MODELS = ["E0", "E1"]

def get_all_model_codes() -> list:
    """获取所有已知产品型号列表（从图片目录动态读取，包含面板型号）"""
    model_list = []
    
    # 添加面板型号
    for panel in PANEL_MODELS:
        if panel not in model_list:
            model_list.append(panel)
    
    # 从知识库目录读取
    if os.path.exists(PRODUCT_KB_DIR):
        for fname in os.listdir(PRODUCT_KB_DIR):
            if fname.endswith('.md'):
                parts = fname.replace('.md', '').split('-')
                for part in parts:
                    if part and part not in model_list:
                        model_list.append(part)
    
    # 从图片目录读取
    if os.path.exists(os.path.join(os.path.dirname(__file__), "assets", "images")):
        images_dir = os.path.join(os.path.dirname(__file__), "assets", "images")
        for item in os.listdir(images_dir):
            item_path = os.path.join(images_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                if item not in model_list:
                    model_list.append(item)
    
    return sorted(model_list)


def is_valid_model(model: str) -> bool:
    """检查型号是否有效（包含桌架型号和面板型号）"""
    model_upper = model.upper().strip()
    return model_upper in [m.upper() for m in get_all_model_codes()]


def _find_kb_file(model: str) -> Optional[str]:
    """查找型号对应的知识库文件"""
    if not os.path.exists(PRODUCT_KB_DIR):
        return None

    model_clean = model.strip()

    for fname in os.listdir(PRODUCT_KB_DIR):
        if not fname.endswith('.md'):
            continue
        parts = fname.replace('.md', '').split('-')
        for part in parts:
            if part.upper() == model_clean.upper():
                return os.path.join(PRODUCT_KB_DIR, fname)

    model_lower = model_clean.lower()
    for fname in os.listdir(PRODUCT_KB_DIR):
        if fname.endswith('.md') and model_lower in fname.lower():
            return os.path.join(PRODUCT_KB_DIR, fname)

    return None
