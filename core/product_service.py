"""
产品图片服务 — 型号查找、图片扫描、选图
从旧 image_knowledge + image_manager 精简而来，
去掉 LLM/Vision 索引（现在由 AI 自己看图），只保留文件系统扫描和发图记录。
"""
import os
import re
import json
import time
from pathlib import Path
from typing import Optional

from config import (
    log, PRODUCT_IMAGES_DIR, CACHE_DIR, BASE_DIR,
)


# ═══════════════════════════════════════════════════════
# 图片扫描
# ═══════════════════════════════════════════════════════

_product_image_cache: dict[str, list[str]] = {}
_cache_last_update: float = 0
_CACHE_TTL: int = 60  # 缓存有效期60秒


def scan_product_images(force_refresh: bool = False) -> dict[str, list[str]]:
    """扫描 assets/images/ 下所有产品目录，返回 {型号: [图片绝对路径列表]}
    
    Args:
        force_refresh: 是否强制刷新缓存
    """
    global _product_image_cache, _cache_last_update
    
    # 检查缓存是否有效
    now = time.time()
    cache_valid = (
        _product_image_cache and 
        not force_refresh and 
        (now - _cache_last_update) < _CACHE_TTL
    )
    
    if cache_valid:
        return _product_image_cache

    cache = {}
    img_root = Path(PRODUCT_IMAGES_DIR)
    if not img_root.is_dir():
        log(f"[产品] 图片目录不存在: {PRODUCT_IMAGES_DIR}")
        return cache

    for folder in img_root.iterdir():
        if not folder.is_dir():
            continue
        images = []
        for fname in sorted(folder.iterdir()):
            if fname.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                images.append(str(fname.resolve()))
        if images:
            cache[folder.name] = images

    _product_image_cache = cache
    _cache_last_update = now
    log(f"[产品] 已扫描 {len(cache)} 个产品目录 (刷新: {force_refresh})")
    return cache


def refresh_product_cache():
    """强制刷新产品图片缓存"""
    global _product_image_cache, _cache_last_update
    _product_image_cache = {}
    _cache_last_update = 0
    log("[产品] 图片缓存已清空，下次访问将重新扫描")
    return scan_product_images(force_refresh=True)


def get_cache_info() -> dict:
    """获取缓存状态信息"""
    now = time.time()
    return {
        "cached_products": len(_product_image_cache),
        "last_update": _cache_last_update,
        "cache_age_seconds": int(now - _cache_last_update) if _cache_last_update else None,
        "cache_valid": (now - _cache_last_update) < _CACHE_TTL if _cache_last_update else False,
        "ttl_seconds": _CACHE_TTL
    }


def find_product_images(model: str) -> list[str]:
    """查找产品图片（统一入口）
    
    查找链：cache → 别名映射（动态加载）
    """
    cache = scan_product_images()

    # 直接匹配
    if model in cache:
        return cache[model]

    # 大小写不敏感
    model_upper = model.upper()
    for dir_name, imgs in cache.items():
        if dir_name.upper() == model_upper:
            return imgs

    # 动态加载型号别名映射
    from config import load_model_aliases
    model_aliases = load_model_aliases()
    mapped = model_aliases.get(model) or model_aliases.get(model_upper)
    if mapped and mapped in cache:
        return cache[mapped]

    # 模糊匹配（仅用于提示，不直接返回，避免错误匹配）
    similar_models = []
    for dir_name, imgs in cache.items():
        if model_upper in dir_name.upper() or dir_name.upper() in model_upper:
            similar_models.append(dir_name)
    
    if similar_models:
        log(f"[产品] 型号 {model} 未找到，但发现相似型号: {similar_models}")
    
    return []


def list_all_products() -> list[dict]:
    """列出所有产品型号及图片数量"""
    cache = scan_product_images()
    result = []
    for model, imgs in sorted(cache.items()):
        result.append({
            "model": model,
            "image_count": len(imgs),
            "images": imgs,
        })
    return result


def search_products(query: str) -> list[dict]:
    """搜索产品型号"""
    cache = scan_product_images()
    query_upper = query.upper()
    results = []
    for model, imgs in sorted(cache.items()):
        if query_upper in model.upper() or model.upper() in query_upper:
            results.append({"model": model, "image_count": len(imgs), "images": imgs})
        else:
            # 动态加载别名并检查
            from config import load_model_aliases
            model_aliases = load_model_aliases()
            for alias, target in model_aliases.items():
                if target == model and query_upper in alias.upper():
                    results.append({"model": model, "alias": alias, "image_count": len(imgs), "images": imgs})
                    break
    return results


# ═══════════════════════════════════════════════════════
# 发图记录（防止重复发图）
# ═══════════════════════════════════════════════════════

SENT_IMAGES_FILE = os.path.join(CACHE_DIR, "_sent_images.json")
SENT_IMAGE_EXPIRE = 7200  # 2小时过期
_sent_images_log: dict = {}


def load_sent_images():
    global _sent_images_log
    data = load_json_data(SENT_IMAGES_FILE)
    if isinstance(data, dict):
        _sent_images_log = data


def save_sent_images():
    save_json_data(SENT_IMAGES_FILE, _sent_images_log)


def record_sent_image(session_id: str, model: str, image_path: str):
    """记录发送的图片"""
    now = time.time()
    rec = _sent_images_log.setdefault(session_id, {})
    rec.setdefault("model_list", [])
    if model not in rec["model_list"]:
        rec["model_list"].append(model)
    rec.setdefault("paths", []).append({"path": image_path, "time": now, "model": model})

    # 清理过期
    rec["paths"] = [
        e for e in rec.get("paths", [])
        if isinstance(e, dict) and (now - e.get("time", 0)) < SENT_IMAGE_EXPIRE
    ]
    save_sent_images()


def get_recent_sent_paths(session_id: str) -> set:
    """获取近期已发图片路径集合"""
    rec = _sent_images_log.get(session_id, {})
    now = time.time()
    recent = set()
    for entry in rec.get("paths", []):
        if isinstance(entry, dict) and (now - entry.get("time", 0)) < SENT_IMAGE_EXPIRE:
            recent.add(entry.get("path", ""))
    return recent


def pick_best_image(model: str, session_id: str = "", prefer_tags: list[str] = None, 
                   specified_index: int = None, sequential: bool = False) -> Optional[str]:
    """选择最佳产品图片
    
    策略优先级：
    1. 客户指定角度 -> 发指定的图
    2. 没指定 -> 智能挑选（角度最好、最清晰）
    3. 要更多 -> 顺序发下一张
    4. 兜底 -> 默认发第一张
    
    Args:
        model: 产品型号
        session_id: 会话ID（用于追踪已发图片）
        prefer_tags: 偏好标签（如["整体图", "侧面"]）
        specified_index: 客户指定的图片序号（0-based）
        sequential: 是否顺序发下一张（True=顺序发，False=智能挑选）
    """
    all_images = find_product_images(model)
    if not all_images:
        return None
    
    # 1. 客户指定角度 -> 发指定的图
    if specified_index is not None and 0 <= specified_index < len(all_images):
        return all_images[specified_index]
    
    # 获取已发图片记录
    recent_sent = set()
    if session_id:
        recent_sent = get_recent_sent_paths(session_id)
    
    # 过滤出未发过的图片
    not_sent = [img for img in all_images if img not in recent_sent]
    if not not_sent:
        # 全发过了，重新开始
        not_sent = all_images
    
    # 2. 没指定 & 不顺序 -> 智能挑选（选文件名最规范的，通常是最清晰的）
    if not sequential and not specified_index:
        # 智能挑选策略：
        # - 优先选带 "_01" "_02" 序号的（正式产品图）
        # - 避免选 "detail" "parts" 等细节图作为首张
        # - 优先选 jpg（通常比 png 小，加载快）
        scored = []
        for img in not_sent:
            score = 0
            fname = os.path.basename(img).lower()
            # 有序号的加分，但 _02/_03 通常是场景图，_01 往往是细节图
            if re.search(r'_0?2|_0?3', fname):  # _02, _03 是场景图，加分最多
                score += 15
            elif re.search(r'_01', fname):  # _01 往往是细节图，加分少
                score += 5
            elif re.search(r'_0?\d+', fname):  # 其他序号正常加分
                score += 10
            # jpg 格式加分
            if fname.endswith('.jpg') or fname.endswith('.jpeg'):
                score += 5
            # 避免细节图作为首张
            if any(tag in fname for tag in ['detail', 'parts', '配件', '螺丝']):
                score -= 20
            # 整体图、主图加分
            if any(tag in fname for tag in ['main', '整体', '主图', 'full']):
                score += 15
            scored.append((score, img))
        
        # 按分数排序，选最高的
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[0][1] if scored else not_sent[0]
    
    # 3. 顺序发下一张 -> 按顺序选第一张未发过的
    if sequential:
        return not_sent[0]
    
    # 4. 兜底 -> 默认发第一张
    return all_images[0]


# ═══════════════════════════════════════════════════════
# 智能发图接口（给外部调用）
# ═══════════════════════════════════════════════════════

def get_next_image_for_customer(model: str, customer_id: str = "", 
                                 request_type: str = "smart") -> tuple[Optional[str], str]:
    """获取下一张要发给客户的图片
    
    Args:
        model: 产品型号
        customer_id: 客户标识（用于追踪已发图片）
        request_type: 请求类型
            - "smart": 智能挑选最佳角度（默认）
            - "next": 顺序发下一张
            - "index:N": 发指定序号（如 "index:0" 发第一张）
    
    Returns:
        (图片路径, 说明文字)
    """
    specified_index = None
    sequential = False
    
    # 解析请求类型
    if request_type.startswith("index:"):
        try:
            specified_index = int(request_type.split(":")[1])
        except (ValueError, IndexError):
            pass
    elif request_type == "next":
        sequential = True
    
    # 调用选图逻辑
    image_path = pick_best_image(
        model=model,
        session_id=customer_id,
        specified_index=specified_index,
        sequential=sequential
    )
    
    if not image_path:
        return None, f"未找到 {model} 的图片"
    
    # 生成说明文字
    all_images = find_product_images(model)
    if image_path in all_images:
        idx = all_images.index(image_path) + 1
        total = len(all_images)
        desc = f"{model} 产品图 ({idx}/{total})"
    else:
        desc = f"{model} 产品图"
    
    return image_path, desc


# ═══════════════════════════════════════════════════════
# 产品知识库文本（给 AI 参考）
# ═══════════════════════════════════════════════════════

# 产品知识库缓存
_product_knowledge_cache: str = ""
_product_knowledge_last_update: float = 0
_PRODUCT_KNOWLEDGE_TTL: int = 300  # 5分钟缓存


def get_product_knowledge_text(force_refresh: bool = False) -> str:
    """生成产品知识库概要文本
    
    Args:
        force_refresh: 是否强制刷新缓存
    """
    global _product_knowledge_cache, _product_knowledge_last_update
    
    # 检查缓存是否有效
    now = time.time()
    cache_valid = (
        _product_knowledge_cache and 
        not force_refresh and 
        (now - _product_knowledge_last_update) < _PRODUCT_KNOWLEDGE_TTL
    )
    
    if cache_valid:
        return _product_knowledge_cache
    
    # 重新生成知识库文本
    cache = scan_product_images()
    lines = ["## 产品图片资源\n"]
    lines.append("型号 -> 可用图片数量:")
    for model in sorted(cache.keys()):
        lines.append(f"  - {model}: {len(cache[model])}张")
    
    # 动态加载型号别名（从配置文件）
    from config import load_model_aliases
    aliases = load_model_aliases()
    if aliases:
        lines.append("\n型号别名映射:")
        for alias, target in sorted(aliases.items()):
            lines.append(f"  - {alias} -> {target}")
    
    # 尝试读取产品描述（支持多个文件）
    products_md = Path(BASE_DIR) / "personas" / "shared" / "products.md"
    if products_md.is_file():
        lines.append("\n" + products_md.read_text(encoding="utf-8"))
    
    # 也检查 assets/products/ 目录下的 .md 文件
    products_dir = Path(BASE_DIR) / "assets" / "products"
    if products_dir.is_dir():
        for md_file in sorted(products_dir.glob("*.md")):
            lines.append(f"\n\n## {md_file.stem}\n")
            lines.append(md_file.read_text(encoding="utf-8"))
    
    result = "\n".join(lines)
    _product_knowledge_cache = result
    _product_knowledge_last_update = now
    
    return result


def refresh_product_knowledge():
    """强制刷新产品知识库缓存"""
    global _product_knowledge_cache, _product_knowledge_last_update
    _product_knowledge_cache = ""
    _product_knowledge_last_update = 0
    log("[产品] 知识库缓存已刷新")
    return get_product_knowledge_text(force_refresh=True)


# ═══════════════════════════════════════════════════════
# JSON 辅助（本地用，不依赖 config 的 load_json）
# ═══════════════════════════════════════════════════════

def load_json_data(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json_data(path: str, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════

load_sent_images()
