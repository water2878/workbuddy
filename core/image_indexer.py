"""
产品图片索引系统
用Vision模型分析产品图片特征，建立索引，支持客户图片比对
"""
import os
import json
import base64
import time
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime

# 导入配置
from config import PRODUCT_IMAGES_DIR as IMAGES_DIR, BASE_DIR, log

# 索引文件路径
IMAGE_INDEX_FILE = os.path.join(BASE_DIR, "data", "image_index.json")

# 全局索引缓存
_image_index: dict = {}
_indexing_lock = threading.Lock()
_is_indexing = False


# ========== 索引管理 ==========

def load_image_index():
    """加载图片索引缓存"""
    global _image_index
    if os.path.exists(IMAGE_INDEX_FILE):
        try:
            with open(IMAGE_INDEX_FILE, "r", encoding="utf-8") as f:
                _image_index = json.load(f)
            log(f"[图片索引] 已加载 {len(_image_index)} 条索引")
        except Exception as e:
            log(f"[图片索引] 加载失败: {e}")
            _image_index = {}
    else:
        _image_index = {}


def save_image_index():
    """保存图片索引"""
    try:
        os.makedirs(os.path.dirname(IMAGE_INDEX_FILE), exist_ok=True)
        with open(IMAGE_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(_image_index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"[图片索引] 保存失败: {e}")


# ========== 图片扫描 ==========

def scan_product_images() -> dict[str, list[str]]:
    """扫描所有产品图片目录，返回 {型号: [图片路径列表]}"""
    cache = {}
    if not os.path.isdir(IMAGES_DIR):
        log(f"[图片索引] 图片目录不存在: {IMAGES_DIR}")
        return cache
    
    for dirname in os.listdir(IMAGES_DIR):
        dirpath = os.path.join(IMAGES_DIR, dirname)
        if not os.path.isdir(dirpath):
            continue
        
        images = []
        for fname in os.listdir(dirpath):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")):
                fpath = os.path.join(dirpath, fname)
                images.append(os.path.abspath(fpath))
        
        if images:
            cache[dirname] = images
    
    log(f"[图片索引] 已扫描 {len(cache)} 个产品目录")
    return cache


# ========== Vision分析 ==========

def _encode_image_to_base64(image_path: str) -> str:
    """将图片转为base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_image_with_vision(image_path: str, model: str = "moonshot-v1-8k-vision-preview") -> Optional[dict]:
    """
    用Vision模型分析图片，提取特征标签
    返回: {"features": [...], "description": "...", "model_hint": "..."}
    """
    try:
        from openai import OpenAI
        
        # 读取API配置
        api_key = os.getenv("MOONSHOT_API_KEY", "")
        if not api_key:
            # 尝试从配置文件读取
            config_path = os.path.join(BASE_DIR, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    api_key = config.get("moonshot_api_key", "")
        
        if not api_key:
            log("[图片索引] 未配置API密钥")
            return None
        
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        
        # 读取图片
        base64_image = _encode_image_to_base64(image_path)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """分析这张升降桌产品图片，提取关键特征。
请用JSON格式返回：
{
    "features": ["特征1", "特征2", ...],
    "description": "简要描述",
    "model_hint": "推测的型号或类型"
}

特征应包括：
- 颜色（白色/黑色/灰色）
- 管型（方管/椭圆管/圆管）
- 电机数（单电机/双电机）
- 结构（正装/倒装）
- 脚型（平脚/弯脚/弓脚/带轮）
- 其他特征（双横梁/线槽/挡板等）"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        content = response.choices[0].message.content
        
        # 解析JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "features": result.get("features", []),
                "description": result.get("description", ""),
                "model_hint": result.get("model_hint", ""),
                "analyzed_at": datetime.now().isoformat()
            }
        return None
        
    except Exception as e:
        log(f"[图片索引] Vision分析失败: {e}")
        return None


# ========== 索引构建 ==========

def index_single_image(image_path: str) -> bool:
    """索引单张图片"""
    if image_path in _image_index:
        # 已索引过，跳过
        return True
    
    result = analyze_image_with_vision(image_path)
    if result:
        _image_index[image_path] = result
        save_image_index()
        log(f"[图片索引] {os.path.basename(image_path)}: {result['features']}")
        return True
    else:
        _image_index[image_path] = {"features": ["failed"], "error": "分析失败"}
        save_image_index()
        return False


def index_all_products(force_reindex: bool = False):
    """索引所有产品图片"""
    global _is_indexing
    
    with _indexing_lock:
        if _is_indexing:
            log("[图片索引] 正在索引中，请稍候...")
            return
        _is_indexing = True
    
    try:
        products = scan_product_images()
        total = sum(len(imgs) for imgs in products.values())
        indexed = 0
        failed = 0
        skipped = 0
        
        log(f"[图片索引] 开始索引 {len(products)} 个型号，共 {total} 张图片...")
        
        for model, images in products.items():
            log(f"[图片索引] 索引型号 {model} ({len(images)} 张)")
            
            for img_path in images:
                if not force_reindex and img_path in _image_index:
                    skipped += 1
                    continue
                
                if index_single_image(img_path):
                    indexed += 1
                else:
                    failed += 1
                
                # 避免API限流
                time.sleep(1)
        
        log(f"[图片索引] 完成! 新索引: {indexed}, 跳过: {skipped}, 失败: {failed}")
        
    finally:
        with _indexing_lock:
            _is_indexing = False


# ========== 图片比对 ==========

def compare_image_features(user_image_path: str, top_k: int = 3) -> list[tuple[str, str, float]]:
    """
    比对客户图片和产品图片
    返回: [(产品型号, 图片路径, 相似度分数), ...]
    """
    # 分析客户图片
    user_features = analyze_image_with_vision(user_image_path)
    if not user_features:
        return []
    
    user_feat_set = set(f.lower() for f in user_features.get("features", []))
    
    results = []
    
    for img_path, data in _image_index.items():
        if "failed" in data.get("features", []):
            continue
        
        img_feat_set = set(f.lower() for f in data.get("features", []))
        
        # 计算Jaccard相似度
        intersection = user_feat_set & img_feat_set
        union = user_feat_set | img_feat_set
        
        if union:
            similarity = len(intersection) / len(union)
        else:
            similarity = 0
        
        # 提取型号
        model = os.path.basename(os.path.dirname(img_path))
        
        results.append((model, img_path, similarity))
    
    # 排序返回top_k
    results.sort(key=lambda x: x[2], reverse=True)
    return results[:top_k]


def find_best_matching_product(user_image_path: str) -> Optional[tuple[str, list[str]]]:
    """
    找出与客户图片最匹配的产品型号
    返回: (产品型号, [推荐图片路径列表]) 或 None
    """
    matches = compare_image_features(user_image_path, top_k=5)
    
    if not matches:
        return None
    
    # 按型号分组
    model_scores: dict[str, list[tuple[str, float]]] = {}
    for model, img_path, score in matches:
        if model not in model_scores:
            model_scores[model] = []
        model_scores[model].append((img_path, score))
    
    # 找出平均分最高的型号
    best_model = None
    best_avg_score = 0
    
    for model, scores in model_scores.items():
        avg_score = sum(s for _, s in scores) / len(scores)
        if avg_score > best_avg_score:
            best_avg_score = avg_score
            best_model = model
    
    if best_model:
        # 返回该型号得分最高的几张图片
        images = [img for img, _ in model_scores[best_model][:3]]
        return best_model, images
    
    return None


# ========== 初始化 ==========

def init_image_indexer():
    """初始化图片索引系统"""
    load_image_index()
    log("[图片索引] 初始化完成")


# 启动时加载
init_image_indexer()
