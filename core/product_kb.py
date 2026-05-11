# -*- coding: utf-8 -*-
"""从产品知识库提取参数的模块"""

import os
import json
import re
from typing import Dict, Optional

# 产品知识库目录（Claw项目结构）
PRODUCT_KB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "products")

# 价格配置文件路径
PRICE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "product_prices.json")


def _load_price_config() -> Dict:
    """加载价格配置文件"""
    if not os.path.exists(PRICE_CONFIG_PATH):
        print(f"[产品知识库] 价格配置文件不存在: {PRICE_CONFIG_PATH}")
        return {}
    
    try:
        with open(PRICE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[产品知识库] 加载价格配置失败: {e}")
        return {}


def get_standard_prices() -> Dict[str, float]:
    """获取产品标准价格表（从配置文件读取）"""
    config = _load_price_config()
    return config.get("prices", {})


# 注意：STANDARD_PRICES 已废弃，请使用 get_standard_prices() 函数
# 为了向后兼容，这里定义为一个 property 类，每次访问都重新读取
class _DynamicPrices(dict):
    """动态价格字典，每次访问都重新读取配置文件"""
    def __getitem__(self, key):
        prices = get_standard_prices()
        return prices.get(key, 0)
    
    def __contains__(self, key):
        prices = get_standard_prices()
        return key in prices
    
    def get(self, key, default=0):
        prices = get_standard_prices()
        return prices.get(key, default)
    
    def __repr__(self):
        return repr(get_standard_prices())

STANDARD_PRICES = _DynamicPrices()


def extract_product_params(model: str) -> Dict[str, str]:
    """
    从产品知识库提取指定型号的参数
    返回包含 color, volume, weight, frame_size 等字段的字典
    """
    # 查找知识库文件
    kb_file = _find_kb_file(model)
    if not kb_file:
        return {}

    # 解析文件内容
    with open(kb_file, 'r', encoding='utf-8') as f:
        content = f.read()

    params = {}

    # 提取钢架颜色（表格格式：| 桌架颜色 | 黑色 / 白色 / 灰色 |）
    color_match = re.search(r'桌架颜色.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if color_match:
        params['color'] = color_match.group(1).strip()
    print(f"[产品知识库] 钢架颜色: {params.get('color', '未找到')}")

    # 提取包装规格（表格格式：| 包装规格 | 2个1050*250*210mm；45KG一件 |）
    packing_match = re.search(r'包装规格.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    packing = packing_match.group(1).strip() if packing_match else ''
    print(f"[产品知识库] 包装规格: {packing}")
    if packing:
        # 提取体积 (长*宽*高 mm)
        vol_match = re.search(r'(\d+)\*(\d+)\*(\d+)\s*mm', packing)
        if vol_match:
            l, w, h = vol_match.groups()
            # 转换为立方米
            volume_m3 = (int(l) * int(w) * int(h)) / 1_000_000_000
            params['volume'] = f"{l}×{w}×{h}mm ({volume_m3:.4f}m³)"

        # 提取重量
        weight_match = re.search(r'(\d+)\s*KG', packing)
        if weight_match:
            params['weight'] = f"{weight_match.group(1)}KG"

    # 提取台架尺寸（横梁伸缩范围）
    frame_match = re.search(r'横梁伸缩范围.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if frame_match:
        params['frame_size'] = frame_match.group(1).strip()
    print(f"[产品知识库] 台架尺寸: {params.get('frame_size', '未找到')}")

    # 提取升降高度范围
    lift_match = re.search(r'升降高度范围.*?\|\s*([^\|]+?)\s*\|', content, re.DOTALL)
    if lift_match:
        params['lift_range'] = lift_match.group(1).strip()

    return {k: v for k, v in params.items() if v}


def get_standard_price(model: str) -> float:
    """获取产品标准价格，如果未找到型号返回0
    
    每次调用都从配置文件读取，确保价格更新后无需重启服务
    """
    prices = get_standard_prices()
    return prices.get(model.upper(), 0)


def _find_kb_file(model: str) -> Optional[str]:
    """查找型号对应的知识库文件"""
    if not os.path.exists(PRODUCT_KB_DIR):
        print(f"[产品知识库] 目录不存在: {PRODUCT_KB_DIR}")
        return None

    model_clean = model.strip()
    print(f"[产品知识库] 查找型号: {model_clean}")
    print(f"[产品知识库] 目录内容: {os.listdir(PRODUCT_KB_DIR)[:5]}")

    # 精确匹配文件名末尾的型号
    for fname in os.listdir(PRODUCT_KB_DIR):
        if not fname.endswith('.md'):
            continue
        # 文件格式: 畅腾AI-单品种知识库-T423.md
        # 提取文件名中的型号
        parts = fname.replace('.md', '').split('-')
        for part in parts:
            if part.upper() == model_clean.upper():
                full_path = os.path.join(PRODUCT_KB_DIR, fname)
                print(f"[产品知识库] 找到文件: {full_path}")
                return full_path

    # 模糊匹配：型号在文件名中
    model_lower = model_clean.lower()
    for fname in os.listdir(PRODUCT_KB_DIR):
        if fname.endswith('.md') and model_lower in fname.lower():
            return os.path.join(PRODUCT_KB_DIR, fname)

    print(f"[产品知识库] 未找到型号 {model_clean} 对应的知识库文件")
    return None


def _extract_field(content: str, pattern: str) -> str:
    """从内容中提取第一个匹配的值"""
    match = re.search(pattern, content, re.DOTALL)
    if match:
        value = match.group(1).strip()
        # 清理表格格式中的 | 符号
        value = re.sub(r'^\|\s*|\s*\|.*$', '', value).strip()
        return value
    return ''


def get_product_info(model: str) -> Optional[Dict]:
    """获取产品信息（含图片目录），供合同生成使用
    
    每个产品型号对应独立的图片目录和知识库，不使用映射
    """
    if not model:
        return None

    # 每个型号使用自己的独立目录
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "images")
    dir_name = model.upper()  # 直接使用型号作为目录名
    img_dir = os.path.join(base_dir, dir_name)

    info = {
        "model": model,
        "image_dir": img_dir if os.path.isdir(img_dir) else None,
        "price": get_standard_price(model),
    }
    # 尝试从知识库提取更多参数
    params = extract_product_params(model)
    info.update(params)

    return info


# 测试
if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    # 测试T423
    params = extract_product_params('T423')
    print('T423 参数:')
    for k, v in params.items():
        print(f'  {k}: {v}')