"""
Vision 图片识别服务 — 使用多模态 LLM 识别客户发来的产品图片
"""
import os
import base64
import json
import requests
from typing import Optional
from pathlib import Path

from config import log, BASE_DIR

# ═══════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════

def _load_moonshot_config() -> tuple[str, str]:
    """从 OpenClaw 配置加载 Moonshot API key"""
    # 1. 优先从环境变量读取
    api_key = os.environ.get("MOONSHOT_API_KEY", "")
    base_url = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    
    if api_key:
        return api_key, base_url
    
    # 2. 从 OpenClaw auth-profiles.json 读取
    try:
        auth_file = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
        if auth_file.exists():
            with open(auth_file, "r", encoding="utf-8") as f:
                auth_data = json.load(f)
                profiles = auth_data.get("profiles", {})
                moonshot_profile = profiles.get("moonshot:default", {})
                if moonshot_profile.get("type") == "api_key":
                    api_key = moonshot_profile.get("key", "")
                    log(f"[Vision] 从 OpenClaw 配置加载 API key")
    except Exception as e:
        log(f"[Vision] 读取 OpenClaw 配置失败: {e}")
    
    # 3. 从 models.json 读取
    if not api_key:
        try:
            models_file = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "models.json"
            if models_file.exists():
                with open(models_file, "r", encoding="utf-8") as f:
                    models_data = json.load(f)
                    moonshot_provider = models_data.get("providers", {}).get("moonshot", {})
                    api_key = moonshot_provider.get("apiKey", "")
                    base_url = moonshot_provider.get("baseUrl", base_url)
                    if api_key:
                        log(f"[Vision] 从 models.json 加载 API key")
        except Exception as e:
            log(f"[Vision] 读取 models.json 失败: {e}")
    
    return api_key, base_url

# 加载配置
MOONSHOT_API_KEY, MOONSHOT_BASE_URL = _load_moonshot_config()
VISION_MODEL = "moonshot-v1-8k-vision-preview"  # 支持图片识别的模型

# ═══════════════════════════════════════════════════════
# 图片编码
# ═══════════════════════════════════════════════════════

def encode_image_to_base64(image_path: str) -> Optional[str]:
    """将图片转为 base64 编码"""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        log(f"[Vision] 图片编码失败: {e}")
        return None


def get_image_mime_type(image_path: str) -> str:
    """根据文件扩展名获取 MIME 类型"""
    ext = Path(image_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_map.get(ext, "image/jpeg")


# ═══════════════════════════════════════════════════════
# Vision 识别
# ═══════════════════════════════════════════════════════

def analyze_product_image(image_path: str) -> dict:
    """
    分析产品图片，识别升降桌型号和特征
    
    返回: {
        "success": bool,
        "description": str,  # 图片描述
        "detected_model": str,  # 识别的型号（如果有）
        "features": dict,  # 识别到的特征
    }
    """
    if not MOONSHOT_API_KEY:
        # 如果没有 API key，返回本地分析结果
        return _local_analyze(image_path)
    
    base64_image = encode_image_to_base64(image_path)
    if not base64_image:
        return {"success": False, "description": "图片编码失败", "detected_model": "", "features": {}}
    
    mime_type = get_image_mime_type(image_path)
    
    # 构建提示词
    system_prompt = """你是畅腾升降桌的产品专家。请仔细分析客户发来的升降桌图片，识别以下信息：

1. 桌腿结构：单电机/双电机、正装/倒装、方管/椭圆管
2. 桌面特征：颜色、材质、形状（矩形/弧形/异形）
3. 整体风格：办公/家用、简约/电竞
4. 可能的型号：根据特征判断最可能对应的产品型号

请用简洁的中文回复，格式如下：
- 桌腿：xxx
- 桌面：xxx
- 风格：xxx
- 推测型号：xxx（相似度：高/中/低）"""

    try:
        headers = {
            "Authorization": f"Bearer {MOONSHOT_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "请分析这张升降桌图片，识别产品型号和特征。"
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(
            f"{MOONSHOT_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            description = result["choices"][0]["message"]["content"]
            
            # 解析型号
            detected_model = _extract_model_from_description(description)
            
            log(f"[Vision] 识别成功: {description[:100]}...")
            
            return {
                "success": True,
                "description": description,
                "detected_model": detected_model,
                "features": _extract_features(description)
            }
        else:
            log(f"[Vision] API 错误: {response.status_code} - {response.text[:200]}")
            return _local_analyze(image_path)
            
    except Exception as e:
        log(f"[Vision] 识别异常: {e}")
        return _local_analyze(image_path)


def _local_analyze(image_path: str) -> dict:
    """本地简单分析（备用方案）"""
    return {
        "success": True,
        "description": "收到您发来的升降桌图片。从图片来看，这是一款现代风格的升降桌。",
        "detected_model": "",
        "features": {"style": "现代办公", "confidence": "low"}
    }


def _extract_model_from_description(description: str) -> str:
    """从描述中提取型号 - 按管型+电机数+结构判断"""
    import re

    # 常见型号模式
    model_patterns = [
        r'[TF]\d{3,4}[A-Z]?',  # T523, F4200, F4404 等
        r'F5S\d{2}',  # F5S系列
    ]

    for pattern in model_patterns:
        matches = re.findall(pattern, description.upper())
        if matches:
            return matches[0]

    # 提取关键特征
    has_double_motor = "双电机" in description
    has_single_motor = "单电机" in description
    has_oval_tube = "椭圆" in description or "椭圆管" in description
    has_square_tube = "方管" in description
    has_inverted = "倒腿" in description or "倒装" in description
    has_normal = "正装" in description

    # 按特征组合判断型号
    if has_double_motor:
        # 双电机系列
        if has_oval_tube:
            return "T621"  # 双电机椭圆管 = T621
        elif has_inverted:
            return "F4200"  # 双电机方管倒装 = F4200
        else:
            return "F4404"  # 双电机方管正装 = F4404
    elif has_single_motor:
        # 单电机系列
        if has_oval_tube:
            return "T523"  # 单电机椭圆管 = T523（倒装）
        elif has_inverted:
            return "T523"  # 单电机方管倒装 = T523
        else:
            return "T524"  # 单电机方管正装 = T524
    elif "手摇" in description:
        return "T728"  # 手摇款 = T728

    return ""


def _extract_features(description: str) -> dict:
    """提取特征"""
    features = {}
    
    # 电机类型
    if "双电机" in description:
        features["motor"] = "双电机"
    elif "单电机" in description:
        features["motor"] = "单电机"
    elif "手摇" in description:
        features["motor"] = "手摇"
    
    # 腿结构
    if "倒腿" in description or "倒装" in description:
        features["leg_structure"] = "倒装"
    elif "正装" in description:
        features["leg_structure"] = "正装"
    
    # 管型
    if "方管" in description:
        features["tube_type"] = "方管"
    elif "椭圆" in description:
        features["tube_type"] = "椭圆管"
    
    # 桌面
    if "弧形" in description or "异形" in description:
        features["desktop_shape"] = "弧形"
    else:
        features["desktop_shape"] = "矩形"
    
    return features


# ═══════════════════════════════════════════════════════
# 快捷函数
# ═══════════════════════════════════════════════════════

def get_product_suggestion(image_path: str) -> str:
    """
    根据图片获取产品推荐建议
    返回给客户看的推荐文案
    """
    result = analyze_product_image(image_path)
    
    if not result["success"]:
        return "收到您的图片！这是升降桌吧？可以告诉我您需要什么配置吗？"
    
    model = result.get("detected_model", "")
    description = result.get("description", "")
    
    # 根据识别的型号生成推荐
    suggestions = {
        "F4200": {
            "name": "双电机方管倒装 F4200",
            "price": "待定",
            "features": "双电机驱动、方管倒装、稳定性好"
        },
        "F4404": {
            "name": "双电机对向座 F4404",
            "price": "1604元",
            "features": "双电机驱动、对向座、3节升降"
        },
        "T523": {
            "name": "单电机方管倒装 T523",
            "price": "460元",
            "features": "单电机、方管倒装、4个记忆、儿童锁"
        },
        "T524": {
            "name": "单电机方管正装 T524",
            "price": "415元",
            "features": "单电机、方管正装、2个记忆"
        },
        "T621": {
            "name": "双电机椭圆管 T621",
            "price": "835元",
            "features": "双电机、椭圆管3节、负载120Kg、高端款"
        },
        "T728": {
            "name": "手摇升降 T728",
            "price": "411元",
            "features": "手摇升降、正装、升降720-1200MM"
        },
        "T412": {
            "name": "双电机方管正装 T412",
            "price": "689元",
            "features": "双电机、方管正装2节、4个记忆、USB、儿童锁"
        },
        "T423": {
            "name": "双电机方管正装3节 T423",
            "price": "775元",
            "features": "双电机、方管正装3节、负载120Kg、4个记忆、USB"
        },
    }
    
    if model and model in suggestions:
        info = suggestions[model]
        return f"""收到您的图片！从图片来看，这像是我们的 **{info['name']}** 系列产品，参考价 **{info['price']}**。

{description}

这款产品{info['features']}，非常适合您的使用场景。请问您需要了解详细配置吗？"""
    else:
        # 通用回复
        return f"""收到您的图片！

{description}

我们有多款升降桌可供选择：
- 单电机款：415元起（T523/T524系列）
- 双电机款：689元起（T412/T423/T621/F4404系列）
- 手摇款：411元（T728系列）

请问您需要什么配置？可以把您的具体需求告诉我。"""


# ═══════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════

def check_vision_available() -> bool:
    """检查 Vision 服务是否可用"""
    return bool(MOONSHOT_API_KEY)
