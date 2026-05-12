"""
Claw 工具 API 服务器
AI 的大脑 → HTTP 调用 → Python 的手脚

启动: python core/app.py
端口: 5032 (默认)
"""
import os
import sys
import json
import traceback
import re
import wave
import subprocess
import threading
import functools
from datetime import datetime
from typing import Dict, Any, Callable, Optional, List
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from config import log, API_HOST, API_PORT, WEFLOW_BASE, WEFLOW_TOKEN, CLOUD_SERVER, CLOUD_TOKEN, SALES_ID, BASE_DIR, MATERIALS_CONTACT
from product_service import (
    find_product_images, list_all_products, search_products,
    pick_best_image, record_sent_image, get_product_knowledge_text,
)
from customer_service import (
    get_customer, save_customer, update_customer_notes,
    add_customer_order, set_customer_preference,
    list_customers, search_customers, touch_customer,
)
from contract.contract_generator import load_contracts, save_contracts, ContractStatus
from image_indexer import (
    index_all_products, find_best_matching_product, compare_image_features,
    load_image_index, _image_index
)

# 导入云端同步客户端（WebSocket版本）
try:
    from cloud_sync_client_ws import CloudSyncWebSocketClient
    CLOUD_SYNC_ENABLED = True
except ImportError:
    CLOUD_SYNC_ENABLED = False
    CloudSyncWebSocketClient = None

app = Flask(__name__)
# 配置CORS，允许特定域名访问
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://120.26.84.224:5032", "http://localhost:*", "http://127.0.0.1:*"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "supports_credentials": True
    }
})


@app.route("/favicon.ico")
def favicon():
    """返回畅腾LOGO作为favicon"""
    favicon_path = os.path.join(BASE_DIR, "assets", "images", "favicon.ico")
    if os.path.exists(favicon_path):
        return send_file(favicon_path, mimetype="image/x-icon")
    # 如果favicon不存在，返回204避免404错误
    return "", 204


@app.before_request
def _log_request():
    if request.path.startswith("/api/"):
        args = ""
        if request.args:
            args = " " + "&".join(f"{k}={v}" for k, v in request.args.items())
        body_hint = ""
        if request.method in ("POST", "PUT") and request.is_json:
            try:
                data = request.get_json(silent=True) or {}
                keys = list(data.keys())[:5]
                body_hint = f" body={{{', '.join(keys)}}}"
            except Exception:
                pass
        log(f"← {request.method} {request.path}{args}{body_hint}", "API")


@app.after_request
def _add_pna_header(response):
    """允许公网页面访问本地API（Chrome Private Network Access）"""
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# ═══════════════════════════════════════════════════════
# AI友好的API工具集
# ═══════════════════════════════════════════════════════

def success_response(data: Any = None, message: str = "") -> Dict:
    """统一成功响应格式"""
    response = {
        "success": True,
        "code": 200,
        "data": data if data is not None else {}
    }
    if message:
        response["message"] = message
    return response


def error_response(error: str, code: int = 400, details: Any = None) -> Dict:
    """统一错误响应格式"""
    response = {
        "success": False,
        "code": code,
        "error": error
    }
    if details:
        response["details"] = details
    return response


def api_handler(func: Callable) -> Callable:
    """API处理装饰器，统一错误处理和响应格式"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, dict) and "success" in result:
                return jsonify(result)
            if isinstance(result, tuple):
                data, status_code = result
                response = jsonify(data)
                response.status_code = status_code
                return response
            return jsonify(success_response(result))
        except ValueError as e:
            return jsonify(error_response(str(e), 400)), 400
        except FileNotFoundError as e:
            return jsonify(error_response(str(e), 404)), 404
        except Exception as e:
            error_msg = str(e)
            trace = traceback.format_exc()
            return jsonify(error_response(error_msg, 500, trace)), 500
    return wrapper


class ParamValidator:
    """参数验证器"""
    
    @staticmethod
    def required(data: Dict, field: str, field_type: type = str) -> Any:
        """验证必填字段"""
        if field not in data or data[field] is None or data[field] == "":
            raise ValueError(f"缺少必填参数: {field}")
        value = data[field]
        if not isinstance(value, field_type):
            try:
                value = field_type(value)
            except (ValueError, TypeError):
                raise ValueError(f"参数 {field} 类型错误，期望 {field_type.__name__}")
        return value
    
    @staticmethod
    def optional(data: Dict, field: str, default: Any = None, field_type: type = None) -> Any:
        """验证可选字段"""
        value = data.get(field, default)
        if value is not None and field_type is not None:
            try:
                value = field_type(value)
            except (ValueError, TypeError):
                raise ValueError(f"参数 {field} 类型错误，期望 {field_type.__name__}")
        return value


# 工具注册表
_tools_registry: Dict[str, Dict] = {}


def register_tool(name: str, description: str, method: str = "POST", endpoint: str = "",
                  params: Dict[str, Dict] = None, returns: Dict[str, Any] = None):
    """注册工具描述"""
    def decorator(func: Callable) -> Callable:
        _tools_registry[name] = {
            "name": name,
            "description": description,
            "method": method,
            "endpoint": endpoint or f"/api/{name.replace('_', '/')}",
            "params": params or {},
            "returns": returns or {"type": "object", "description": "操作结果"}
        }
        return func
    return decorator


# ═══════════════════════════════════════════════════════
# 资料员通知功能（产品缺少图片时）
# ═══════════════════════════════════════════════════════

# 已通知过的产品型号（避免重复通知）
_notified_missing_products: set = set()


def notify_materials_staff(model: str, reason: str = "缺少产品图片") -> bool:
    """通知资料员补充产品资料
    
    Args:
        model: 产品型号
        reason: 缺少的原因
    
    Returns:
        bool: 是否成功发送通知
    """
    log(f"[资料员通知] 开始通知流程 - 型号: {model}, 资料员: {MATERIALS_CONTACT}")
    
    if not MATERIALS_CONTACT:
        log(f"[资料员通知] 未配置资料员联系人，跳过通知")
        return False
    
    try:
        from sender.wechat_sender import send_text_safe
        
        # 生成管理页面链接
        materials_url = f"http://{API_HOST}:{API_PORT}/materials"
        
        message = f"""📢 资料补充提醒

产品型号：{model}
缺少内容：{reason}
请求时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

👉 点击链接补充资料：
{materials_url}

请尽快上传产品图片，谢谢！"""
        
        log(f"[资料员通知] 正在发送消息给 {MATERIALS_CONTACT}")
        result = send_text_safe(MATERIALS_CONTACT, message)
        
        if result.get("success"):
            log(f"[资料员通知] 已通知资料员补充 {model} 的资料")
            return True
        else:
            log(f"[资料员通知] 发送失败: {result.get('error')}")
            return False
            
    except Exception as e:
        log(f"[资料员通知] 异常: {e}")
        import traceback
        log(f"[资料员通知] 异常堆栈: {traceback.format_exc()}")
        return False


# ═══════════════════════════════════════════════════════
# WeFlow 客户端（懒加载）
# ═══════════════════════════════════════════════════════

_weflow_client = None


def get_weflow():
    global _weflow_client
    if _weflow_client is None:
        from weflow_client import WeFlowClient
        _weflow_client = WeFlowClient(WEFLOW_BASE, WEFLOW_TOKEN)
    return _weflow_client


# ═══════════════════════════════════════════════════════
# 语音识别（本地 SenseVoice via sherpa-onnx）
# ═══════════════════════════════════════════════════════

_sherpa_recognizer = None
VOICE_MODEL_DIR = os.environ.get("VOICE_MODEL_DIR", r"C:\Users\Lenovo\sherpa_sensevoice")


def _ensure_wav(voice_path: str) -> str:
    """确保语音文件是 WAV 格式（16kHz, 16bit, mono）"""
    try:
        with open(voice_path, "rb") as f:
            header = f.read(12)
            is_wav = header[:4] == b"RIFF" and header[8:12] == b"WAVE"
        if is_wav:
            return voice_path
    except Exception:
        pass

    # 需要转换格式
    wav_path = voice_path + ".wav"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", voice_path, "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", "-y", wav_path],
            capture_output=True, timeout=30
        )
        if result.returncode == 0 and os.path.isfile(wav_path):
            return wav_path
    except Exception as e:
        log(f"[语音] ffmpeg转换失败: {e}")
    return None


def _transcribe_via_sherpa(voice_path: str) -> str:
    """用本地 sherpa-onnx (SenseVoice) 模型转文字"""
    global _sherpa_recognizer

    model_onnx = os.path.join(VOICE_MODEL_DIR, "model.int8.onnx")
    tokens_txt = os.path.join(VOICE_MODEL_DIR, "tokens.txt")

    if not all(os.path.isfile(p) for p in [model_onnx, tokens_txt]):
        log(f"[语音] 本地模型不完整: {VOICE_MODEL_DIR}")
        return ""

    wav_path = _ensure_wav(voice_path)
    if not wav_path:
        log(f"[语音] 无法转为WAV格式")
        return ""

    try:
        log(f"[语音] 本地sherpa识别中...")

        if _sherpa_recognizer is None:
            import sherpa_onnx
            _sherpa_recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model_onnx, tokens=tokens_txt,
                num_threads=2, use_itn=True, debug=False,
            )
            log("[语音] sherpa模型已加载")

        import numpy as np
        with wave.open(wav_path, 'rb') as f:
            sample_rate = f.getframerate()
            frames = f.readframes(f.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        stream = _sherpa_recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples.tolist())
        _sherpa_recognizer.decode_stream(stream)

        text = stream.result.text.strip() if stream.result else ""

        if text and len(text) > 1:
            # 清理特殊标签
            tags = [r'<\|zh\|>', r'<\|en\|>', r'<\|ja\|>', r'<\|ko\|>', r'<\|yue\|>',
                    r'<\|nospeech\|>', r'<\|speech\|>', r'<\|itn\|>', r'<\|wo_itn\|>', r'<\|NORMAL\|>']
            for tag in tags:
                text = re.sub(tag, '', text)
            emo_map = {'<|HAPPY|>': '😊', '<|SAD|>': '😔', '<|ANGRY|>': '😠',
                       '<|FEARFUL|>': '😨', '<|SURPRISED|>': '😮', '<|NEUTRAL|>': ''}
            for tag, emoji in emo_map.items():
                text = text.replace(tag, emoji)
            text = re.sub(r'\s+', ' ', text).strip()

            log(f"[语音→文字] {text}")
            return text
        else:
            log(f"[语音] 识别结果为空")
    except Exception as e:
        log(f"[语音] sherpa异常: {e}")

    return ""


def transcribe_voice(voice_path: str) -> str:
    """语音转文字入口"""
    if not os.path.isfile(voice_path):
        return "[语音文件不存在]"
    result = _transcribe_via_sherpa(voice_path)
    return result if result else "[语音识别失败]"


# ═══════════════════════════════════════════════════════
# Health & AI工具发现
# ═══════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify(success_response({
        "service": "claw-tool-server",
        "weflow": WEFLOW_BASE,
        "version": "2.0",
        "ai_ready": True
    }))


@app.route("/api/tools", methods=["GET"])
def list_tools():
    """获取所有可用工具描述（供AI自动发现）"""
    tools = {
        "send_text": {
            "name": "send_text",
            "description": "发送文字消息到微信联系人",
            "endpoint": "/api/send/text",
            "method": "POST",
            "params": {
                "contact": {"type": "string", "description": "联系人名称或微信昵称", "required": True},
                "message": {"type": "string", "description": "要发送的消息内容", "required": True}
            },
            "returns": {"type": "object", "description": "发送结果"}
        },
        "send_file": {
            "name": "send_file",
            "description": "发送文件到微信联系人",
            "endpoint": "/api/send/file",
            "method": "POST",
            "params": {
                "contact": {"type": "string", "description": "联系人名称", "required": True},
                "file_path": {"type": "string", "description": "本地文件绝对路径", "required": True},
                "message": {"type": "string", "description": "可选的附加消息", "required": False}
            }
        },
        "send_product_image": {
            "name": "send_product_image",
            "description": "一键发送产品图片（自动选图+发送+记录）",
            "endpoint": "/api/send-product-image",
            "method": "POST",
            "params": {
                "contact": {"type": "string", "description": "联系人名称", "required": True},
                "model": {"type": "string", "description": "产品型号，如T523、F4200", "required": True},
                "session_id": {"type": "string", "description": "会话ID（可选）", "required": False}
            }
        },
        "search_products": {
            "name": "search_products",
            "description": "搜索产品信息",
            "endpoint": "/api/products/search",
            "method": "GET",
            "params": {
                "q": {"type": "string", "description": "搜索关键词，如型号T523", "required": False}
            }
        },
        "get_product_images": {
            "name": "get_product_images",
            "description": "获取指定型号的产品图片列表",
            "endpoint": "/api/products/{model}/images",
            "method": "GET",
            "params": {
                "model": {"type": "string", "description": "产品型号", "required": True}
            }
        },
        "match_image": {
            "name": "match_image",
            "description": "比对客户发来的图片，找出最匹配的产品型号",
            "endpoint": "/api/image/match",
            "method": "POST",
            "params": {
                "image_path": {"type": "string", "description": "客户图片的本地路径", "required": True}
            }
        },
        "transcribe_voice": {
            "name": "transcribe_voice",
            "description": "将语音文件转写成文字",
            "endpoint": "/api/transcribe",
            "method": "POST",
            "params": {
                "voice_path": {"type": "string", "description": "语音文件本地路径", "required": True}
            }
        },
        "get_latest_voice": {
            "name": "get_latest_voice",
            "description": "获取联系人最新发送的语音并转文字",
            "endpoint": "/api/latest-voice",
            "method": "GET",
            "params": {
                "contact": {"type": "string", "description": "联系人名称", "required": True}
            }
        },
        "get_latest_image": {
            "name": "get_latest_image",
            "description": "获取联系人最新发送的图片",
            "endpoint": "/api/latest-image",
            "method": "GET",
            "params": {
                "contact": {"type": "string", "description": "联系人名称", "required": True}
            }
        },
        "get_chat_history": {
            "name": "get_chat_history",
            "description": "获取与联系人的聊天记录",
            "endpoint": "/api/chat-history/{session_id}",
            "method": "GET",
            "params": {
                "session_id": {"type": "string", "description": "会话ID", "required": True},
                "limit": {"type": "integer", "description": "返回消息数量", "required": False, "default": 50},
                "keyword": {"type": "string", "description": "关键词筛选", "required": False}
            }
        },
        "get_customer": {
            "name": "get_customer",
            "description": "获取客户信息和画像",
            "endpoint": "/api/customers/{contact_id}",
            "method": "GET",
            "params": {
                "contact_id": {"type": "string", "description": "客户ID或昵称", "required": True}
            }
        },
        "update_customer_notes": {
            "name": "update_customer_notes",
            "description": "更新客户备注",
            "endpoint": "/api/customers/{contact_id}/notes",
            "method": "POST",
            "params": {
                "contact_id": {"type": "string", "description": "客户ID", "required": True},
                "notes": {"type": "string", "description": "备注内容", "required": True}
            }
        },
        "generate_contract": {
            "name": "generate_contract",
            "description": "生成销售合同并推送云端审批。客户确认订单后调用，需要提供客户信息和产品明细",
            "endpoint": "/api/contracts/generate",
            "method": "POST",
            "params": {
                "company_name": {"type": "string", "description": "公司名称（乙方）", "required": True},
                "customer_contact": {"type": "string", "description": "联系人姓名", "required": True},
                "customer_phone": {"type": "string", "description": "联系电话", "required": True},
                "customer_address": {"type": "string", "description": "收货地址", "required": True},
                "products": {"type": "array", "description": "产品列表 [{model, quantity, unit_price, subtotal}]", "required": True},
                "session_id": {"type": "string", "description": "微信会话ID", "required": False},
                "customer_wxid": {"type": "string", "description": "客户微信ID", "required": False},
                "customer_nickname": {"type": "string", "description": "客户微信昵称", "required": False},
                "delivery_date": {"type": "string", "description": "交货日期", "required": False},
                "payment_terms": {"type": "string", "description": "付款方式", "required": False},
                "notes": {"type": "string", "description": "备注（颜色、面板等）", "required": False}
            }
        },
        "list_contracts": {
            "name": "list_contracts",
            "description": "获取合同列表",
            "endpoint": "/api/contracts/list",
            "method": "GET",
            "params": {}
        },
        "get_contract_detail": {
            "name": "get_contract_detail",
            "description": "获取合同详情",
            "endpoint": "/api/contracts/detail/{contract_id}",
            "method": "GET",
            "params": {
                "contract_id": {"type": "string", "description": "合同ID", "required": True}
            }
        },
        "text_to_image": {
            "name": "text_to_image",
            "description": "将长文字生成图片（适合微信发送）",
            "endpoint": "/api/text-to-image",
            "method": "POST",
            "params": {
                "title": {"type": "string", "description": "标题", "required": False},
                "lines": {"type": "array", "description": "内容行列表", "required": True},
                "footer": {"type": "string", "description": "底部文字", "required": False}
            }
        },
        "store_memory": {
            "name": "store_memory",
            "description": "存储记忆到向量数据库",
            "endpoint": "/api/memory/store",
            "method": "POST",
            "params": {
                "text": {"type": "string", "description": "记忆内容", "required": True},
                "source": {"type": "string", "description": "来源", "required": False},
                "type": {"type": "string", "description": "记忆类型", "required": False, "default": "chat"},
                "customer": {"type": "string", "description": "关联客户", "required": False}
            }
        },
        "search_memory": {
            "name": "search_memory",
            "description": "语义搜索记忆",
            "endpoint": "/api/memory/search",
            "method": "POST",
            "params": {
                "query": {"type": "string", "description": "搜索查询", "required": True},
                "top_k": {"type": "integer", "description": "返回数量", "required": False, "default": 5},
                "customer": {"type": "string", "description": "按客户筛选", "required": False}
            }
        }
    }
    return jsonify(success_response({
        "tools": list(tools.values()),
        "count": len(tools),
        "base_url": f"http://{API_HOST}:{API_PORT}"
    }))


@app.route("/api/batch", methods=["POST"])
@api_handler
def batch_execute():
    """批量执行多个API调用
    
    Body: {
        "operations": [
            {"tool": "send_text", "params": {"contact": "张三", "message": "你好"}},
            {"tool": "search_products", "params": {"q": "T523"}}
        ],
        "continue_on_error": true
    }
    """
    data = request.json or {}
    operations = ParamValidator.required(data, "operations", list)
    continue_on_error = ParamValidator.optional(data, "continue_on_error", True, bool)
    
    if not operations:
        raise ValueError("operations 不能为空列表")
    
    # 工具路由映射
    tool_routes = {
        "send_text": ("/api/send/text", "POST"),
        "send_file": ("/api/send/file", "POST"),
        "send_product_image": ("/api/send-product-image", "POST"),
        "search_products": ("/api/products/search", "GET"),
        "get_product_images": ("/api/products/{model}/images", "GET"),
        "match_image": ("/api/image/match", "POST"),
        "transcribe_voice": ("/api/transcribe", "POST"),
        "get_latest_voice": ("/api/latest-voice", "GET"),
        "get_latest_image": ("/api/latest-image", "GET"),
        "get_customer": ("/api/customers/{contact_id}", "GET"),
        "update_customer_notes": ("/api/customers/{contact_id}/notes", "POST"),
        "text_to_image": ("/api/text-to-image", "POST"),
        "store_memory": ("/api/memory/store", "POST"),
        "search_memory": ("/api/memory/search", "POST"),
    }
    
    results = []
    errors = []
    success_count = 0
    
    with app.test_client() as client:
        for i, op in enumerate(operations):
            tool_name = op.get("tool", "")
            params = op.get("params", {})
            
            if tool_name not in tool_routes:
                error_msg = f"未知工具: {tool_name}"
                results.append({
                    "index": i,
                    "tool": tool_name,
                    "success": False,
                    "error": error_msg
                })
                errors.append(error_msg)
                if not continue_on_error:
                    break
                continue
            
            route, method = tool_routes[tool_name]
            
            # 替换路径参数
            for key, value in params.items():
                placeholder = "{" + key + "}"
                if placeholder in route:
                    route = route.replace(placeholder, str(value))
            
            try:
                if method == "GET":
                    resp = client.get(route, query_string=params)
                else:
                    # POST时移除路径参数
                    body_params = {k: v for k, v in params.items() if "{" + k + "}" not in tool_routes[tool_name][0]}
                    resp = client.post(route, json=body_params)
                
                result_data = resp.get_json() or {"raw": resp.data.decode()}
                success = result_data.get("success", resp.status_code == 200)
                
                results.append({
                    "index": i,
                    "tool": tool_name,
                    "success": success,
                    "status_code": resp.status_code,
                    "data": result_data
                })
                
                if success:
                    success_count += 1
                else:
                    errors.append(f"{tool_name}: {result_data.get('error', '未知错误')}")
                    
            except Exception as e:
                error_msg = f"{tool_name}: {str(e)}"
                results.append({
                    "index": i,
                    "tool": tool_name,
                    "success": False,
                    "error": str(e)
                })
                errors.append(error_msg)
                
                if not continue_on_error:
                    break
    
    return success_response({
        "total": len(operations),
        "success": success_count,
        "failed": len(operations) - success_count,
        "results": results,
        "errors": errors
    })


# ═══════════════════════════════════════════════════════
# 消息发送
# ═══════════════════════════════════════════════════════

@app.route("/api/send/text", methods=["POST"])
@api_handler
def send_text():
    """发送文字消息到微信联系人
    
    Body: {"contact": "联系人名", "message": "消息内容"}
    """
    data = request.json or {}
    contact = ParamValidator.required(data, "contact", str)
    message = ParamValidator.required(data, "message", str)
    
    from sender.wechat_sender import send_text_safe
    result = send_text_safe(contact, message)
    
    if result.get("success"):
        log(f"[发文字] -> {contact}: {message[:50]}...")
        return success_response(result, "消息发送成功")
    else:
        raise ValueError(result.get("error", "发送失败"))


# ═══════════════════════════════════════════════════════
# 图片索引与比对
# ═══════════════════════════════════════════════════════

@app.route("/api/image/index", methods=["POST"])
@api_handler
def image_index():
    """构建所有产品图片的Vision索引
    
    Body: {"force": false}  (可选，是否强制重新索引)
    """
    data = request.json or {}
    force = ParamValidator.optional(data, "force", False, bool)
    
    def do_index():
        index_all_products(force_reindex=force)
    
    threading.Thread(target=do_index, daemon=True).start()
    
    return success_response(
        {"force": force},
        "索引任务已启动，请在日志中查看进度"
    )


@app.route("/api/image/match", methods=["POST"])
@api_handler
def image_match():
    """比对客户图片，找出最匹配的产品
    
    Body: {"image_path": "客户图片路径"}
    返回: {"success": true, "best_match": {"model": "型号", "images": [...], "confidence": 0.85}}
    """
    data = request.json or {}
    image_path = ParamValidator.required(data, "image_path", str)
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")
    
    result = find_best_matching_product(image_path)
    
    if result:
        model, images = result
        # 计算相似度
        matches = compare_image_features(image_path, top_k=5)
        avg_score = sum(score for _, _, score in matches[:3]) / min(3, len(matches))
        
        return success_response({
            "best_match": {
                "model": model,
                "images": images,
                "confidence": round(avg_score, 2)
            },
            "all_matches": [
                {"model": m, "image": i, "score": round(s, 2)} 
                for m, i, s in matches
            ]
        })
    else:
        return success_response(
            {"matches": []},
            "未找到匹配的产品，建议手动选择型号"
        )


@app.route("/api/image/index/status", methods=["GET"])
@api_handler
def image_index_status():
    """获取图片索引状态"""
    return success_response({
        "indexed_images": len(_image_index),
        "index_file_exists": os.path.exists(os.path.join(BASE_DIR, "data", "image_index.json")),
        "ready": len(_image_index) > 0
    })


@app.route("/api/send/file", methods=["POST"])
@api_handler
def send_wechat_file():
    """发送文件到微信联系人
    
    Body: {"contact": "联系人名", "file_path": "文件路径", "message": "可选说明"}
    """
    data = request.json or {}
    contact = ParamValidator.required(data, "contact", str)
    file_path = ParamValidator.required(data, "file_path", str)
    message = ParamValidator.optional(data, "message", "", str)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    from sender.wechat_sender import send_file_safe
    result = send_file_safe(contact, file_path)
    
    if result.get("success"):
        log(f"[发文件] -> {contact}: {os.path.basename(file_path)}")
        return success_response(result, "文件发送成功")
    else:
        raise ValueError(result.get("error", "发送失败"))


# ═══════════════════════════════════════════════════════
# 产品图片
# ═══════════════════════════════════════════════════════

@app.route("/api/products", methods=["GET"])
@api_handler
def list_products():
    """列出所有产品"""
    products = list_all_products()
    return success_response({
        "products": products,
        "count": len(products)
    })


@app.route("/api/products/search", methods=["GET"])
@api_handler
def search_products_api():
    """搜索产品
    
    Query: ?q=T523
    """
    query = request.args.get("q", "")
    if not query:
        products = list_all_products()
    else:
        products = search_products(query)
    
    return success_response({
        "query": query,
        "products": products,
        "count": len(products)
    })


@app.route("/api/products/<model>/images", methods=["GET"])
@api_handler
def product_images(model):
    """获取产品图片列表"""
    images = find_product_images(model)
    if not images:
        # 通知资料员补充资料
        notified = notify_materials_staff(model, f"查询型号 {model} 图片列表，但该产品缺少图片资料")
        
        response_data = {
            "model": model,
            "images": [],
            "count": 0,
            "notified": notified
        }
        
        message = "该产品暂无图片"
        if notified:
            message += "，已通知资料员补充"
        
        return success_response(response_data, message)
    
    return success_response({
        "model": model,
        "images": images,
        "count": len(images)
    })


@app.route("/api/products/<model>/pick-image", methods=["GET"])
@api_handler
def pick_product_image(model):
    """为产品选择最佳图片
    
    Query: ?session_id=xxx
    """
    log(f"[API] pick_product_image 被调用 - 型号: {model}")
    
    session_id = request.args.get("session_id", "")
    image_path = pick_best_image(model, session_id)
    
    log(f"[API] pick_product_image 结果 - 型号: {model}, 找到图片: {bool(image_path)}")
    
    if not image_path:
        log(f"[API] pick_product_image 图片不存在，准备通知资料员")
        # 通知资料员补充资料
        notified = notify_materials_staff(model, f"为型号 {model} 选择最佳图片，但该产品缺少图片资料")
        
        error_msg = f"型号 {model} 无可用图片"
        if notified:
            error_msg += "，已通知资料员补充"
        
        log(f"[API] pick_product_image 返回错误: {error_msg}")
        raise FileNotFoundError(error_msg)
    
    log(f"[API] pick_product_image 返回成功 - 图片: {image_path}")
    return success_response({
        "model": model,
        "image_path": image_path,
        "session_id": session_id
    })


@app.route("/api/products/knowledge", methods=["GET"])
@api_handler
def product_knowledge():
    """获取产品知识库文本（给 AI 参考）"""
    text = get_product_knowledge_text()
    return success_response({
        "text": text,
        "length": len(text)
    })


@app.route("/api/images/serve", methods=["GET"])
def serve_image():
    """提供图片文件（AI 可预览）
    
    Query: ?path=图片绝对路径
    """
    path = request.args.get("path", "")
    if not path or not os.path.exists(path):
        return "图片不存在", 404

    from config import MIME_MAP
    ext = os.path.splitext(path)[1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")
    return send_file(path, mimetype=mime)


# ═══════════════════════════════════════════════════════
# 资料员产品资料管理API
# ═══════════════════════════════════════════════════════

@app.route("/api/materials/missing-products", methods=["GET"])
@api_handler
def get_missing_products():
    """获取缺少图片的产品列表（资料员使用）
    
    Query: ?include_notified=true  (是否包含已通知的)
    """
    include_notified = request.args.get("include_notified", "false").lower() == "true"
    
    # 获取所有产品型号（从产品知识库目录）
    products_dir = Path(BASE_DIR) / "assets" / "products"
    all_models = set()
    
    if products_dir.exists():
        for f in products_dir.glob("*.md"):
            # 从文件名提取型号，如 "畅腾AI-单品种知识库-T523.md" -> "T523"
            match = re.search(r'-([A-Z0-9]+)\.md$', f.name, re.IGNORECASE)
            if match:
                all_models.add(match.group(1).upper())
    
    # 获取已有图片的产品
    from product_service import scan_product_images
    cache = scan_product_images()
    models_with_images = set(k.upper() for k in cache.keys())
    
    # 找出缺少图片的产品
    missing = []
    for model in all_models:
        if model not in models_with_images:
            # 检查是否已通知过
            notify_key = f"{model}:{datetime.now().strftime('%Y%m%d')}"
            was_notified = notify_key in _notified_missing_products
            
            if include_notified or not was_notified:
                missing.append({
                    "model": model,
                    "notified": was_notified,
                    "image_count": 0
                })
    
    # 添加已有图片但数量不足的产品
    for model, imgs in cache.items():
        if len(imgs) < 3:  # 少于3张图认为需要补充
            missing.append({
                "model": model,
                "notified": False,
                "image_count": len(imgs),
                "needs_more": True
            })
    
    return success_response({
        "missing_products": sorted(missing, key=lambda x: x["model"]),
        "count": len(missing),
        "total_products": len(all_models),
        "products_with_images": len(models_with_images)
    })


@app.route("/api/materials/upload", methods=["POST"])
@api_handler
def upload_product_image():
    """上传产品图片（资料员使用）
    
    Body: multipart/form-data
        - model: 产品型号
        - image: 图片文件
        - description: 图片描述（可选）
    """
    model = request.form.get("model", "").strip().upper()
    if not model:
        raise ValueError("缺少产品型号")
    
    if "image" not in request.files:
        raise ValueError("缺少图片文件")
    
    file = request.files["image"]
    if file.filename == "":
        raise ValueError("未选择文件")
    
    # 检查文件类型
    allowed_ext = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise ValueError(f"不支持的文件类型: {ext}，请上传图片文件")
    
    # 创建产品目录
    from config import PRODUCT_IMAGES_DIR
    product_dir = Path(PRODUCT_IMAGES_DIR) / model
    product_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名
    description = request.form.get("description", "").strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if description:
        safe_desc = re.sub(r'[^\w\u4e00-\u9fff]+', '_', description)[:20]
        filename = f"{model}_{safe_desc}_{timestamp}{ext}"
    else:
        filename = f"{model}_{timestamp}{ext}"
    
    # 保存文件到本地
    filepath = product_dir / filename
    file.save(str(filepath))
    
    # 上传到云端（如果启用）
    cloud_url = None
    try:
        from cloud_image_service import upload_image_to_cloud
        cloud_url = upload_image_to_cloud(model, str(filepath), filename)
    except Exception as e:
        log(f"[资料员] 云端上传失败（将使用本地）: {e}")
    
    # 刷新缓存，让新图片立即生效
    from product_service import refresh_product_cache
    refreshed_cache = refresh_product_cache()
    
    log(f"[资料员] 已上传 {model} 的图片: {filename}，缓存已刷新")
    
    result = {
        "model": model,
        "filename": filename,
        "path": str(filepath),
        "size": os.path.getsize(filepath)
    }
    
    if cloud_url:
        result["cloud_url"] = cloud_url
    
    return success_response(result, "图片上传成功")


# ═══════════════════════════════════════════════════════
# 资料员产品管理 API（注意：路由顺序很重要，更具体的路由在前）
# ═══════════════════════════════════════════════════════

@app.route("/api/materials/products", methods=["GET"])
@api_handler
def get_all_products_for_materials():
    """获取所有产品资料状态（资料员使用）"""
    from product_service import scan_product_images
    cache = scan_product_images()
    
    # 获取所有产品型号（从产品知识库）
    products_dir = Path(BASE_DIR) / "assets" / "products"
    all_products = []
    
    if products_dir.exists():
        for f in sorted(products_dir.glob("*.md")):
            match = re.search(r'-([A-Z0-9]+)\.md$', f.name, re.IGNORECASE)
            if match:
                model = match.group(1).upper()
                images = cache.get(model, [])
                
                all_products.append({
                    "model": model,
                    "has_images": len(images) > 0,
                    "image_count": len(images),
                    "images": images[:5],  # 最多返回5张
                })
    
    return success_response({
        "products": all_products,
        "total": len(all_products),
        "with_images": sum(1 for p in all_products if p["has_images"]),
        "without_images": sum(1 for p in all_products if not p["has_images"])
    })


@app.route("/api/materials/products/<model>/images", methods=["GET"])
@api_handler
def get_product_images_for_materials(model):
    """获取指定产品的所有图片（资料员使用）"""
    from product_service import find_product_images
    images = find_product_images(model)
    
    # 获取图片详细信息
    image_details = []
    for img_path in images:
        try:
            stat = os.stat(img_path)
            image_details.append({
                "path": img_path,
                "filename": os.path.basename(img_path),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        except:
            pass
    
    return success_response({
        "model": model,
        "images": image_details,
        "count": len(image_details)
    })


@app.route("/api/materials/products/<model>/images/<path:image_path>", methods=["DELETE"])
@api_handler
def delete_product_image(model, image_path):
    """删除产品图片（资料员使用）
    
    image_path: 图片的相对路径（相对于产品目录）
    """
    from config import PRODUCT_IMAGES_DIR
    
    # 构建完整路径
    full_path = Path(PRODUCT_IMAGES_DIR) / model / image_path
    
    # 安全检查：确保路径在产品图片目录内
    try:
        full_path.relative_to(Path(PRODUCT_IMAGES_DIR))
    except ValueError:
        raise ValueError("非法路径")
    
    if not full_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")
    
    # 移动到回收站（重命名）
    trash_dir = Path(PRODUCT_IMAGES_DIR) / ".trash" / model
    trash_dir.mkdir(parents=True, exist_ok=True)
    
    trash_path = trash_dir / f"{full_path.stem}.deleted.{datetime.now().strftime('%Y%m%d_%H%M%S')}{full_path.suffix}"
    full_path.rename(trash_path)
    
    # 刷新缓存
    from product_service import refresh_product_cache
    refresh_product_cache()
    
    log(f"[资料员] 已删除 {model} 的图片: {image_path}")
    
    return success_response({
        "model": model,
        "filename": image_path,
        "trash_path": str(trash_path)
    }, "图片已删除")


@app.route("/api/materials/refresh-cache", methods=["POST"])
@api_handler
def refresh_materials_cache():
    """手动刷新产品图片缓存"""
    from product_service import refresh_product_cache
    refreshed = refresh_product_cache()
    return success_response({
        "refreshed_products": len(refreshed),
        "products": list(refreshed.keys())
    }, "缓存已刷新")


@app.route("/api/materials/cache-status", methods=["GET"])
@api_handler
def get_materials_cache_status():
    """获取产品图片缓存状态"""
    from product_service import get_cache_info, scan_product_images
    cache_info = get_cache_info()
    current_cache = scan_product_images()
    return success_response({
        "cache_info": cache_info,
        "cached_products": list(current_cache.keys()),
        "product_count": len(current_cache)
    })


# ═══════════════════════════════════════════════════════
# 型号别名管理API（动态配置）
# ═══════════════════════════════════════════════════════

@app.route("/api/materials/aliases", methods=["GET"])
@api_handler
def get_model_aliases():
    """获取所有型号别名映射"""
    from config import load_model_aliases
    aliases = load_model_aliases()
    return success_response({
        "aliases": aliases,
        "count": len(aliases)
    })


@app.route("/api/materials/aliases", methods=["POST"])
@api_handler
def add_model_alias():
    """添加型号别名映射
    
    Body: {"alias": "别名", "target": "目标型号"}
    示例: {"alias": "T-523", "target": "T523"}
    """
    from config import load_model_aliases, save_model_aliases
    
    data = request.json or {}
    alias = ParamValidator.required(data, "alias", str).strip().upper()
    target = ParamValidator.required(data, "target", str).strip().upper()
    
    if alias == target:
        raise ValueError("别名不能与目标型号相同")
    
    aliases = load_model_aliases()
    aliases[alias] = target
    save_model_aliases(aliases)
    
    # 刷新产品缓存，让别名立即生效
    from product_service import refresh_product_cache
    refresh_product_cache()
    
    return success_response({
        "alias": alias,
        "target": target
    }, f"已添加别名: {alias} -> {target}")


@app.route("/api/materials/aliases/<alias>", methods=["DELETE"])
@api_handler
def delete_model_alias(alias):
    """删除型号别名映射"""
    from config import load_model_aliases, save_model_aliases
    
    alias = alias.strip().upper()
    aliases = load_model_aliases()
    
    if alias not in aliases:
        raise FileNotFoundError(f"别名不存在: {alias}")
    
    target = aliases.pop(alias)
    save_model_aliases(aliases)
    
    # 刷新产品缓存
    from product_service import refresh_product_cache
    refresh_product_cache()
    
    return success_response({
        "alias": alias,
        "target": target
    }, f"已删除别名: {alias}")


@app.route("/api/materials/aliases/refresh", methods=["POST"])
@api_handler
def refresh_model_aliases():
    """重新加载型号别名配置"""
    from config import load_model_aliases
    from product_service import refresh_product_cache
    
    aliases = load_model_aliases()
    refresh_product_cache()
    
    return success_response({
        "aliases": aliases,
        "count": len(aliases)
    }, "别名配置已刷新")


@app.route("/api/materials/knowledge/refresh", methods=["POST"])
@api_handler
def refresh_product_knowledge_api():
    """刷新产品知识库缓存"""
    from product_service import refresh_product_knowledge
    knowledge_text = refresh_product_knowledge()
    return success_response({
        "length": len(knowledge_text),
        "preview": knowledge_text[:500] + "..." if len(knowledge_text) > 500 else knowledge_text
    }, "产品知识库已刷新")


@app.route("/api/materials/knowledge/files", methods=["GET"])
@api_handler
def list_knowledge_files():
    """获取所有产品知识库文件列表"""
    products_dir = Path(BASE_DIR) / "assets" / "products"
    files = []
    
    if products_dir.exists():
        for f in sorted(products_dir.glob("*.md")):
            stat = f.stat()
            files.append({
                "filename": f.name,
                "path": str(f),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    
    # 也检查主知识库文件
    main_knowledge = Path(BASE_DIR) / "personas" / "shared" / "products.md"
    if main_knowledge.exists():
        stat = main_knowledge.stat()
        files.insert(0, {
            "filename": "products.md (主知识库)",
            "path": str(main_knowledge),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "is_main": True
        })
    
    return success_response({
        "files": files,
        "count": len(files),
        "directory": str(products_dir)
    })


@app.route("/api/materials/knowledge/files/<filename>", methods=["GET"])
@api_handler
def get_knowledge_file(filename):
    """获取产品知识库文件内容"""
    # 解码 URL 编码的文件名
    filename = filename.replace("%20", " ")
    
    # 支持主知识库文件
    if filename == "products.md" or filename == "products.md (主知识库)":
        file_path = Path(BASE_DIR) / "personas" / "shared" / "products.md"
    else:
        file_path = Path(BASE_DIR) / "assets" / "products" / filename
    
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {filename}")
    
    content = file_path.read_text(encoding="utf-8")
    
    return success_response({
        "filename": filename,
        "content": content,
        "size": len(content),
        "path": str(file_path)
    })


@app.route("/api/materials/knowledge/files/<filename>", methods=["POST"])
@api_handler
def save_knowledge_file(filename):
    """保存产品知识库文件内容
    
    Body: {"content": "文件内容"}
    """
    data = request.json or {}
    content = ParamValidator.required(data, "content", str)
    
    # 解码 URL 编码的文件名
    filename = filename.replace("%20", " ")
    
    # 安全检查：只允许 .md 文件
    if not filename.endswith(".md"):
        raise ValueError("只允许保存 .md 文件")
    
    # 支持主知识库文件
    if filename == "products.md":
        file_path = Path(BASE_DIR) / "personas" / "shared" / "products.md"
    else:
        file_path = Path(BASE_DIR) / "assets" / "products" / filename
    
    # 确保目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 备份原文件
    if file_path.exists():
        backup_path = file_path.with_suffix(f".md.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        file_path.rename(backup_path)
        log(f"[知识库] 已备份原文件: {backup_path.name}")
    
    # 保存新内容
    file_path.write_text(content, encoding="utf-8")
    
    # 刷新缓存
    from product_service import refresh_product_knowledge
    refresh_product_knowledge()
    
    log(f"[知识库] 已保存文件: {filename}")
    
    return success_response({
        "filename": filename,
        "size": len(content),
        "path": str(file_path)
    }, "文件保存成功")


@app.route("/api/materials/knowledge/files/<filename>", methods=["DELETE"])
@api_handler
def delete_knowledge_file(filename):
    """删除产品知识库文件"""
    # 解码 URL 编码的文件名
    filename = filename.replace("%20", " ")
    
    # 不支持删除主知识库文件
    if filename == "products.md" or filename == "products.md (主知识库)":
        raise ValueError("不能删除主知识库文件")
    
    file_path = Path(BASE_DIR) / "assets" / "products" / filename
    
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {filename}")
    
    # 移动到回收站（重命名）
    trash_path = file_path.with_suffix(f".md.deleted.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    file_path.rename(trash_path)
    
    # 刷新缓存
    from product_service import refresh_product_knowledge
    refresh_product_knowledge()
    
    log(f"[知识库] 已删除文件: {filename}")
    
    return success_response({
        "filename": filename,
        "trash_path": str(trash_path)
    }, "文件已删除")


@app.route("/api/materials/knowledge/files", methods=["POST"])
@api_handler
def create_knowledge_file():
    """创建新的产品知识库文件
    
    Body: {"filename": "新文件名.md", "content": "文件内容"}
    """
    data = request.json or {}
    filename = ParamValidator.required(data, "filename", str)
    content = ParamValidator.optional(data, "content", "", str)
    
    # 安全检查
    if not filename.endswith(".md"):
        raise ValueError("文件名必须以 .md 结尾")
    
    # 清理文件名
    filename = filename.replace(" ", "_")
    
    file_path = Path(BASE_DIR) / "assets" / "products" / filename
    
    if file_path.exists():
        raise ValueError(f"文件已存在: {filename}")
    
    # 确保目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    file_path.write_text(content, encoding="utf-8")
    
    # 刷新缓存
    from product_service import refresh_product_knowledge
    refresh_product_knowledge()
    
    log(f"[知识库] 已创建文件: {filename}")
    
    return success_response({
        "filename": filename,
        "size": len(content),
        "path": str(file_path)
    }, "文件创建成功")


# ═══════════════════════════════════════════════════════
# 语音识别（AI 收到 [语音] 后调此接口转文字）
# ═══════════════════════════════════════════════════════




@app.route("/api/transcribe", methods=["POST"])
@api_handler
def transcribe():
    """语音转文字
    
    Body: {"voice_path": "本地语音文件路径"}
    返回: {"text": "转写结果"}
    """
    data = request.json or {}
    voice_path = ParamValidator.required(data, "voice_path", str)

    if not os.path.isfile(voice_path):
        raise FileNotFoundError(f"语音文件不存在: {voice_path}")

    text = transcribe_voice(voice_path)
    return success_response({
        "text": text,
        "voice_path": voice_path
    })


@app.route("/api/latest-voice", methods=["GET"])
@api_handler
def latest_voice():
    """获取联系人最新发送的语音消息并转文字
    
    Query: ?contact=联系人名
    返回: {"text": "转写结果", "voice_path": "本地路径"}
    """
    contact = request.args.get("contact", "")
    if not contact:
        raise ValueError("缺少 contact 参数")

    wf = get_weflow()
    # 先找会话的 talker（username）
    sessions_data = wf.get_sessions(keyword=contact, limit=5)
    sessions_list = []
    if isinstance(sessions_data, dict):
        sessions_list = sessions_data.get("sessions", [])
    elif isinstance(sessions_data, list):
        sessions_list = sessions_data

    talker = None
    if sessions_list:
        for s in sessions_list:
            name = s.get("displayName", "") or s.get("name", "") or s.get("talkerName", "") or ""
            if contact in name or name in contact:
                talker = s.get("username", "") or s.get("sessionId", "") or s.get("talker", "")
                break
        if not talker and sessions_list:
            s = sessions_list[0]
            talker = s.get("username", "") or s.get("sessionId", "") or s.get("talker", "")

    if not talker:
        raise FileNotFoundError(f"未找到 {contact} 的会话")

    # 查最近消息，找语音
    data = wf.get_messages(talker=talker, limit=10, media=True)
    messages = data.get("messages", []) if isinstance(data, dict) else data

    # 找最新的语音消息（消息列表按时间倒序，第一条是最新的）
    for msg in messages:
        local_type = msg.get("localType") or msg.get("local_type", 0)
        content = msg.get("content", "")
        is_voice = (local_type == 34 or local_type == "34" or
                   "语音" in content or "voice" in str(msg.get("mediaType", "")).lower())

        if is_voice:
            local_path = msg.get("mediaLocalPath") or ""
            media_url = msg.get("mediaUrl") or ""

            # 优先本地路径
            if local_path and os.path.isfile(local_path):
                voice_path = local_path
            elif media_url:
                voice_path = wf.download_media(media_url)
            else:
                continue

            if voice_path and os.path.isfile(voice_path):
                # 转文字
                text = transcribe_voice(voice_path)
                return success_response({
                    "text": text,
                    "voice_path": voice_path,
                    "talker": talker,
                })

    raise FileNotFoundError("未找到语音消息")


# ═══════════════════════════════════════════════════════
# 获取客户最新图片（AI 收到 [图片] 后调此接口补全）
# ═══════════════════════════════════════════════════════

@app.route("/api/latest-image", methods=["GET"])
@api_handler
def latest_image():
    """获取联系人最新发送的图片
    
    Query: ?contact=联系人名
    返回: {"image_path": "本地路径", "image_url": "远程URL"}
    """
    contact = request.args.get("contact", "")
    if not contact:
        raise ValueError("缺少 contact 参数")

    wf = get_weflow()
    # 先找会话的 talker（username）
    sessions_data = wf.get_sessions(keyword=contact, limit=5)
    sessions_list = []
    if isinstance(sessions_data, dict):
        sessions_list = sessions_data.get("sessions", [])
    elif isinstance(sessions_data, list):
        sessions_list = sessions_data

    talker = None
    if sessions_list:
        for s in sessions_list:
            name = s.get("displayName", "") or s.get("name", "") or s.get("talkerName", "") or ""
            if contact in name or name in contact:
                talker = s.get("username", "") or s.get("sessionId", "") or s.get("talker", "")
                break
        if not talker and sessions_list:
            s = sessions_list[0]
            talker = s.get("username", "") or s.get("sessionId", "") or s.get("talker", "")

    if not talker:
        raise FileNotFoundError(f"未找到 {contact} 的会话")

    # 查最近消息，找图片
    data = wf.get_messages(talker=talker, limit=10, media=True)
    messages = data.get("messages", []) if isinstance(data, dict) else data

    for msg in reversed(messages):
        local_type = msg.get("localType") or msg.get("local_type", 0)
        content = msg.get("content", "")
        is_image = (local_type == 3 or "图片" in content or
                   msg.get("mediaType") == "image" or msg.get("mediaUrl"))

        if is_image:
            local_path = msg.get("mediaLocalPath") or ""
            media_url = msg.get("mediaUrl") or ""

            # 优先本地路径
            if local_path and os.path.isfile(local_path):
                return success_response({
                    "image_path": local_path,
                    "image_url": media_url,
                    "talker": talker,
                })

            # 下载远程图片
            if media_url:
                downloaded = wf.download_media(media_url)
                if downloaded:
                    return success_response({
                        "image_path": downloaded,
                        "image_url": media_url,
                        "talker": talker,
                    })

    raise FileNotFoundError("未找到图片消息")


# ═══════════════════════════════════════════════════════
# 聊天记录（WeFlow API 代理）
# ═══════════════════════════════════════════════════════

@app.route("/api/chat-history/<session_id>", methods=["GET"])
@api_handler
def chat_history(session_id):
    """获取聊天记录
    
    Query: ?limit=50&keyword=xxx
    """
    limit = int(request.args.get("limit", "50"))
    keyword = request.args.get("keyword", "")

    wf = get_weflow()
    data = wf.get_messages(talker=session_id, limit=limit, keyword=keyword or None, media=True)
    messages = data.get("messages", [])
    
    return success_response({
        "session_id": session_id,
        "messages": messages,
        "count": len(messages),
        "keyword": keyword
    })


@app.route("/api/chat/reply", methods=["POST"])
@api_handler
def chat_reply():
    """获取 AI 回复
    
    Body: {
        "contact": "联系人名",
        "message": "消息内容",
        "is_image": false,
        "voice_path": "",
        "image_path": ""
    }
    """
    data = request.json or {}
    contact = ParamValidator.required(data, "contact", str)
    message = ParamValidator.optional(data, "message", "", str)
    is_image = ParamValidator.optional(data, "is_image", False, bool)
    voice_path = ParamValidator.optional(data, "voice_path", "", str)
    image_path = ParamValidator.optional(data, "image_path", "", str)
    
    # 如果是语音且有路径，先识别
    if voice_path and os.path.exists(voice_path):
        log(f"[chat_reply] Transcribing voice: {voice_path}")
        transcribed = transcribe_voice(voice_path)
        if transcribed and not transcribed.startswith("["):
            message = transcribed
            log(f"[chat_reply] Voice transcribed: {message}")
    
    # 尝试从 message 中提取图片路径
    if is_image and not image_path:
        import re
        match = re.search(r'Path:\s*(.+?)(?:\n|$)', message)
        if match:
            image_path = match.group(1).strip()
            log(f"[chat_reply] Extracted image path from message: {image_path}")
    
    # 生成回复
    reply = generate_ai_reply(contact, message, is_image, image_path)
    
    return success_response({
        "contact": contact,
        "message": message,
        "reply": reply,
        "vision_used": is_image and image_path and os.path.exists(image_path),
    })


def generate_ai_reply(contact: str, message: str, is_image: bool = False, image_path: str = "") -> str:
    """生成 AI 回复（集成 Vision 图片识别）"""
    
    # 简单的规则回复
    msg_lower = message.lower()
    
    # 问候语
    if any(kw in msg_lower for kw in ["你好", "您好", "在吗", "在?", "在？", "hi", "hello"]):
        return "您好！我是客服李胜，有什么可以帮您？"
    
    # 图片消息
    if is_image or "[图片]" in message:
        return "收到您的图片！请问您想了解哪款产品？可以提供具体型号或描述一下配置需求。"
    
    # 语音消息
    if "[语音]" in message:
        # 提取语音内容（如果有）
        voice_content = message.replace("[语音]", "").replace("Path:", "").strip()
        if voice_content and len(voice_content) > 5:
            return f"收到您的语音：「{voice_content}」。请问您想了解哪款产品？"
        return "收到您的语音，但我这边听不太清楚，您方便打字吗？或者说说您想要什么配置的升降桌？"
    
    # 合同相关
    if "合同" in msg_lower:
        return "您好！请提供客户名称、联系人、电话、地址、产品型号数量和价格，我会为您生成合同。"
    
    # 价格相关
    if any(kw in msg_lower for kw in ["价格", "多少钱", "报价", "怎么卖"]):
        return """我们的升降桌价格如下：

📋 **单电机款**：680元起
   - T523/T524 系列，方管结构，性价比高

📋 **双电机款**：750元起  
   - F4200 倒腿款 / F4404 正装款，稳定性好

📋 **手摇款**：380元起
   - 经济实用，无需电源

批量采购有优惠！您需要什么型号？"""
    
    # 型号相关
    if any(kw in msg_lower for kw in ["型号", "有哪些", "有什么"]):
        return """我们有以下主要型号：

🔹 **单电机系列**
   - T523/T524（方管，680元）
   - T621（椭圆管，720元）

🔹 **双电机系列**
   - F4200（倒腿款，750元）
   - F4404（正装款，780元）
   - T728（椭圆管，800元）

您需要哪种配置？可以发图片给我，我帮您识别型号。"""
    
    # 特定型号询问
    model_keywords = {
        "t523": "T523 是单电机方管款，价格680元。性价比较高，适合家用和轻度办公。",
        "t524": "T524 和 T523 类似，也是单电机方管款，价格680元。",
        "f4200": "F4200 是双电机倒腿款，价格750元。双电机驱动更稳定，倒腿设计美观。",
        "f4404": "F4404 是双电机正装款，价格780元。正装结构承重力更强。",
        "t621": "T621 是单电机椭圆管款，价格720元。椭圆管外观更简洁现代。",
        "t728": "T728 是双电机椭圆管款，价格800元。高端配置，大气稳重。",
    }
    
    for model_key, model_reply in model_keywords.items():
        if model_key in msg_lower:
            return f"{model_reply} 您需要了解更详细的参数吗？"
    
    # 默认回复
    return """您好！我是畅腾升降桌客服李胜。

我可以帮您：
💬 查询产品价格
💬 了解不同型号区别
💬 识别升降桌图片型号
💬 生成销售合同

请问您需要什么帮助？"""


@app.route("/api/contacts", methods=["GET"])
@api_handler
def contacts():
    """获取联系人列表
    
    Query: ?keyword=xxx&limit=100
    """
    keyword = request.args.get("keyword", "")
    limit = int(request.args.get("limit", "100"))

    wf = get_weflow()
    data = wf.get_contacts(keyword=keyword or None, limit=limit)
    return success_response(data)


@app.route("/api/sessions", methods=["GET"])
@api_handler
def sessions():
    """获取会话列表
    
    Query: ?keyword=xxx&limit=100
    """
    keyword = request.args.get("keyword", "")
    limit = int(request.args.get("limit", "100"))

    wf = get_weflow()
    data = wf.get_sessions(keyword=keyword or None, limit=limit)
    return success_response(data)


# ═══════════════════════════════════════════════════════
# 客户记忆
# ═══════════════════════════════════════════════════════

@app.route("/api/customers", methods=["GET"])
@api_handler
def list_customers_api():
    """列出所有客户
    
    Query: ?q=搜索关键词
    """
    query = request.args.get("q", "")
    if query:
        customers = search_customers(query)
    else:
        customers = list_customers()
    
    return success_response({
        "customers": customers,
        "count": len(customers),
        "query": query
    })


@app.route("/api/customers/<contact_id>", methods=["GET"])
@api_handler
def get_customer_api(contact_id):
    """获取客户信息"""
    customer = get_customer(contact_id)
    return success_response(customer)


@app.route("/api/customers/<contact_id>", methods=["POST"])
@api_handler
def save_customer_api(contact_id):
    """保存客户信息
    
    Body: {"name": "xxx", "notes": "xxx", "preferences": {}}
    """
    data = request.json or {}
    customer = save_customer(contact_id, data)
    return success_response(customer, "客户信息保存成功")


@app.route("/api/customers/<contact_id>/notes", methods=["POST"])
@api_handler
def update_notes(contact_id):
    """更新客户备注
    
    Body: {"notes": "备注内容"}
    """
    data = request.json or {}
    notes = ParamValidator.required(data, "notes", str)
    customer = update_customer_notes(contact_id, notes)
    return success_response(customer, "备注更新成功")


@app.route("/api/customers/<contact_id>/order", methods=["POST"])
@api_handler
def add_order(contact_id):
    """添加客户订单
    
    Body: {"products": "xxx", "amount": 123, ...}
    """
    data = request.json or {}
    customer = add_customer_order(contact_id, data)
    return success_response(customer, "订单添加成功")


@app.route("/api/customers/<contact_id>/touch", methods=["POST"])
@api_handler
def touch_contact(contact_id):
    """记录客户最近联系时间"""
    data = request.json or {}
    name = ParamValidator.optional(data, "name", "", str)
    customer = touch_customer(contact_id, name)
    return success_response(customer, "联系时间已更新")


# ═══════════════════════════════════════════════════════
# 客户画像同步审批（推送到客户无忧）
# ═══════════════════════════════════════════════════════

# 导入客户同步模块
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.customer_sync import (
    create_sync_record, approve_record, reject_record, push_to_kehu51,
    get_pending_list, get_approved_list, get_sent_list, get_record, update_record,
    profile_to_kehu51_data
)


@app.route("/api/customers/pending", methods=["GET"])
@api_handler
def api_customers_pending():
    """获取待审批的客户画像列表"""
    return success_response(get_pending_list())


@app.route("/api/customers/approved", methods=["GET"])
@api_handler
def api_customers_approved():
    """获取已审批的客户画像列表"""
    return success_response(get_approved_list())


@app.route("/api/customers/sent", methods=["GET"])
@api_handler
def api_customers_sent():
    """获取已推送的客户画像列表"""
    return success_response(get_sent_list())


@app.route("/api/customers/detail/<record_id>", methods=["GET"])
@api_handler
def api_customers_detail(record_id):
    """获取客户画像详情"""
    record = get_record(record_id)
    if record:
        return success_response(record)
    raise FileNotFoundError("记录不存在")


@app.route("/api/customers/approve/<record_id>", methods=["POST"])
@api_handler
def api_customers_approve(record_id):
    """审批通过客户画像"""
    data = request.json or {}
    approved_by = ParamValidator.optional(data, "approved_by", "", str)
    
    if approve_record(record_id, approved_by):
        return success_response({"record_id": record_id}, "审批通过")
    raise ValueError("记录不存在或已处理")


@app.route("/api/customers/reject/<record_id>", methods=["POST"])
@api_handler
def api_customers_reject(record_id):
    """拒绝客户画像"""
    data = request.json or {}
    reason = ParamValidator.optional(data, "reason", "", str)
    
    if reject_record(record_id, reason):
        return success_response({"record_id": record_id}, "已拒绝")
    raise ValueError("记录不存在或已处理")


@app.route("/api/customers/delete/<record_id>", methods=["POST"])
@api_handler
def api_customers_delete(record_id):
    """删除客户画像记录（删除后可重新从客户画像推送）"""
    from core.customer_sync import delete_record
    
    if delete_record(record_id):
        return success_response({"record_id": record_id}, "已删除，可从客户画像重新推送")
    raise FileNotFoundError("记录不存在")


@app.route("/api/customers/push/<record_id>", methods=["POST"])
@api_handler
def api_customers_push(record_id):
    """推送到客户无忧"""
    result = push_to_kehu51(record_id)
    if result.get("success"):
        return success_response(result, "推送成功")
    raise ValueError(result.get("error", "推送失败"))


@app.route("/api/customers/update/<record_id>", methods=["POST"])
@api_handler
def api_customers_update(record_id):
    """更新客户画像信息（审批前可编辑）"""
    updates = request.json or {}
    
    if update_record(record_id, updates):
        return success_response({"record_id": record_id}, "更新成功")
    raise ValueError("记录不存在或已审批")


@app.route("/api/customers/submit", methods=["POST"])
@api_handler
def api_customers_submit():
    """提交客户画像到审批队列"""
    data = request.json or {}
    
    customer_id = ParamValidator.required(data, "customer_id", str)
    customer_nickname = ParamValidator.optional(data, "customer_nickname", "", str)
    profile = ParamValidator.optional(data, "profile", {}, dict)
    
    record = create_sync_record(customer_id, customer_nickname, profile)
    return success_response({
        "record_id": record.id,
        "customer_id": customer_id
    }, "已提交审批")


# ═══════════════════════════════════════════════════════
# 客户画像自动推送 API
# ═══════════════════════════════════════════════════════

@app.route("/api/customers/push/all", methods=["POST"])
@api_handler
def push_all_profiles_api():
    """手动触发推送所有本地客户画像到云端审批系统
    
    Body: {"force": false}  // force=true 时推送所有数据（包括不完整的）
    """
    data = request.json or {}
    force = data.get("force", False)
    
    from core.customer_sync import push_all_profiles_to_cloud, CLOUD_APPROVAL_SERVER
    
    result = push_all_profiles_to_cloud(
        cloud_server=CLOUD_APPROVAL_SERVER,
        filter_complete=not force
    )
    
    return success_response(result, result.get("message", "推送完成"))


@app.route("/api/customers/push/<customer_id>", methods=["POST"])
@api_handler
def push_single_profile_api(customer_id: str):
    """推送单个客户画像到云端审批系统"""
    from core.customer_sync import push_profile_by_customer_id, CLOUD_APPROVAL_SERVER
    
    result = push_profile_by_customer_id(
        customer_id=customer_id,
        cloud_server=CLOUD_APPROVAL_SERVER
    )
    
    if result.get("success"):
        return success_response(result, "推送成功")
    else:
        return error_response(result.get("error", "推送失败"))


@app.route("/api/customers/profiles", methods=["GET"])
@api_handler
def list_local_profiles_api():
    """列出所有本地客户画像"""
    from core.customer_sync import load_local_customer_profiles, is_profile_complete
    
    profiles = load_local_customer_profiles()
    
    result = []
    for profile in profiles:
        result.append({
            "customer_id": profile.get("customer_id"),
            "nickname": profile.get("nickname"),
            "first_contact": profile.get("first_contact"),
            "priority": profile.get("priority"),
            "is_complete": is_profile_complete(profile),
            "_source_file": profile.get("_source_file")
        })
    
    return success_response(result)


@app.route("/api/customers/sync/enable", methods=["POST"])
@api_handler
def enable_auto_sync_api():
    """启用自动推送"""
    global auto_sync_enabled
    auto_sync_enabled = True
    return success_response(message="自动推送已启用")


@app.route("/api/customers/sync/disable", methods=["POST"])
@api_handler
def disable_auto_sync_api():
    """禁用自动推送"""
    global auto_sync_enabled
    auto_sync_enabled = False
    return success_response(message="自动推送已禁用")


@app.route("/api/customers/sync/status", methods=["GET"])
@api_handler
def get_auto_sync_status_api():
    """获取自动推送状态"""
    from core.customer_sync import CLOUD_APPROVAL_SERVER
    return success_response({
        "enabled": auto_sync_enabled,
        "interval": auto_sync_interval,
        "cloud_server": CLOUD_APPROVAL_SERVER
    })


@app.route("/api/customers/sync-from-profiles", methods=["POST"])
@api_handler
def api_customers_sync_from_profiles():
    """从客户画像实时读取并创建同步记录（已推送的跳过，数据不完整的跳过）"""
    import os
    import json
    from core.customer_sync import (
        sync_profile_if_not_exists, get_synced_customer_ids,
        is_profile_complete, get_profile_completeness
    )
    
    CHAT_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "chat_history")
    
    synced_count = 0
    updated_count = 0
    skipped_synced = 0
    skipped_incomplete = 0
    errors = []
    incomplete_customers = []
    
    # 获取已推送的客户ID
    synced_ids = get_synced_customer_ids()
    log(f"[SYNC] Already synced customers: {len(synced_ids)}")
    
    # 遍历所有客户画像文件
    for filename in os.listdir(CHAT_HISTORY_DIR):
        if not filename.endswith("_profile.json"):
            continue
        if filename == "customer_profile_template.json":
            continue
        
        filepath = os.path.join(CHAT_HISTORY_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                profile = json.load(f)
            
            customer_id = profile.get("customer_id", "")
            customer_nickname = profile.get("nickname", "")
            
            if not customer_id:
                continue
            
            # 检查是否已经推送过
            if customer_id in synced_ids:
                log(f"[SYNC] Skip {customer_nickname} ({customer_id}): already synced")
                skipped_synced += 1
                continue
            
            # 检查数据是否完整
            if not is_profile_complete(profile):
                completeness = get_profile_completeness(profile)
                log(f"[SYNC] Skip {customer_nickname} ({customer_id}): profile incomplete")
                skipped_incomplete += 1
                incomplete_customers.append({
                    "nickname": customer_nickname,
                    "customer_id": customer_id,
                    "completeness": completeness
                })
                continue
            
            # 创建或更新同步记录
            record = sync_profile_if_not_exists(customer_id, customer_nickname, profile)
            if record:
                log(f"[SYNC] Created sync record for {customer_nickname}: {record.id}")
                synced_count += 1
            else:
                # 记录已存在但数据已更新
                updated_count += 1
                
        except Exception as e:
            error_msg = f"Error processing {filename}: {str(e)}"
            log(f"[SYNC ERROR] {error_msg}")
            errors.append(error_msg)
    
    return success_response({
        "synced_count": synced_count,           # 新创建的记录数
        "skipped_synced": skipped_synced,       # 已推送的（跳过）
        "skipped_queue": updated_count,         # 已在队列中的（跳过）
        "skipped_incomplete": skipped_incomplete,  # 数据不完整的（跳过）
        "incomplete_customers": incomplete_customers[:10],  # 最多返回10个不完整的
        "errors": errors
    }, "同步完成")


# ═══════════════════════════════════════════════════════
# 合同（本地审批 + 本地发送，与AI助手同架构）
# ═══════════════════════════════════════════════════════

# ── SSE 客户端集合（合同状态变更通知）──
# Flask SSE 用生成器，通过 queue 通知各客户端
import queue as _queue_mod
_contract_sse_clients: dict = {}  # {id(client): client_queue}
_contract_sse_client_counter = 0


def _notify_contract_sse():
    """通知所有 SSE 客户端合同状态变化"""
    dead = []
    for cid, q in _contract_sse_clients.items():
        try:
            q.put("update", timeout=1)
        except Exception:
            dead.append(cid)
    for cid in dead:
        _contract_sse_clients.pop(cid, None)


# ── 本地只读接口（列表/详情走云端代理，本地作为辅助）──

@app.route("/api/contracts/list", methods=["GET"])
def api_contracts_list():
    """合同列表：代理到云端（权威数据），本地兜底"""
    return proxy_contracts("list")


@app.route("/api/contracts/pending", methods=["GET"])
def api_contracts_pending():
    """待审批合同列表：代理到云端"""
    return proxy_contracts("pending")


@app.route("/api/contracts/detail/<contract_id>", methods=["GET"])
def api_contracts_detail(contract_id):
    """合同详情：代理到云端"""
    return proxy_contracts(f"detail/{contract_id}")


@app.route("/api/contracts/pdf/<contract_id>", methods=["GET"])
def api_contracts_pdf(contract_id):
    """合同PDF：代理到云端（云端可能有编辑后的版本）"""
    return proxy_contracts(f"pdf/{contract_id}")


@app.route("/api/contracts/summary", methods=["GET"])
def api_contracts_summary():
    """合同汇总统计：代理到云端"""
    return proxy_contracts("summary")


# ── 合同生成（AI调用入口）──

@app.route("/api/contracts/generate", methods=["POST"])
def api_contracts_generate():
    """生成合同：接收订单数据 → 推送云端自动生成 → 云端审批

    Body: {
        "company_name": "公司名",
        "customer_contact": "联系人",
        "customer_phone": "电话",
        "customer_address": "地址",
        "products": [{"model": "T412", "quantity": 10, "unit_price": 750, "subtotal": 7500}],
        "session_id": "wxid_xxx",
        "customer_wxid": "wxid_xxx",
        "customer_nickname": "昵称",
        "delivery_date": "2026-05-20",
        "payment_terms": "预付30%",
        "voltage": "220V/50Hz",
        "plug_type": "国标",
        "shipping_country": "中国",
        "notes": "备注"
    }
    """
    data = request.json or {}
    log(f"[合同生成] 收到生成请求: 公司={data.get('company_name', '?')}, "
        f"联系人={data.get('customer_contact', '?')}, "
        f"产品数={len(data.get('products', []))}")

    products = data.get("products", [])
    if not products:
        log("[合同生成] 失败: 缺少产品信息")
        return jsonify({"success": False, "error": "缺少产品信息（products不能为空）"}), 400

    if not CLOUD_SERVER:
        log("[合同生成] 失败: 未配置云端服务器")
        return jsonify({"success": False, "error": "未配置云端服务器（CLOUD_SERVER）"}), 503

    try:
        import requests as req

        payload = {**data, "agent_id": SALES_ID or "claw"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CLOUD_TOKEN}",
        }

        cloud_url = f"{CLOUD_SERVER.rstrip('/')}/api/contracts/sync"
        log(f"[合同生成] 推送数据到云端: {cloud_url}")

        resp = req.post(
            cloud_url, json=payload, headers=headers, timeout=30,
            proxies={"http": None, "https": None},
        )

        if resp.status_code == 200:
            result = resp.json()
            contract_id = result.get("contract_id", "")
            log(f"[合同生成] 云端生成成功: 合同号={contract_id}")
            _notify_contract_sse()
            return jsonify(success_response({
                "contract_id": contract_id,
                "status": "pending",
                "created": result.get("created", True),
            }, message="合同已推送云端生成并进入审批流程"))
        else:
            log(f"[合同生成] 云端返回错误: HTTP {resp.status_code} - {resp.text[:200]}")
            return jsonify({"success": False, "error": f"云端返回 HTTP {resp.status_code}: {resp.text[:200]}"}), 502

    except Exception as e:
        log(f"[合同生成] 异常: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"合同生成失败: {e}"}), 500


# ── approve/reject 不在本地处理，走 proxy_contracts 代理到云端 ──
# 云端审批 → 云端回调本机 → 下载云端PDF → 本地发送


@app.route("/api/contracts/update", methods=["POST"])
def api_contracts_update():
    """更新合同：代理到云端"""
    return proxy_contracts("update")


@app.route("/api/contracts/mark-sent", methods=["POST"])
def api_contracts_mark_sent():
    """标记合同已发送：代理到云端"""
    return proxy_contracts("mark-sent")


@app.route("/api/contracts/upload-image", methods=["POST"])
def api_contracts_upload_image():
    """上传合同图片：代理到云端"""
    return proxy_contracts("upload-image")


# ── SSE 推送（合同状态变更实时通知审批页面）──

@app.route("/api/contracts/events", methods=["GET"])
def api_contracts_events():
    """合同状态变更 SSE 推送"""
    import time as _time

    def stream():
        global _contract_sse_client_counter
        _contract_sse_client_counter += 1
        client_id = _contract_sse_client_counter
        q = _queue_mod.Queue()
        _contract_sse_clients[client_id] = q
        try:
            yield f"data: connected\n\n"
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {msg}\n\n"
                except _queue_mod.Empty:
                    yield f"data: heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            _contract_sse_clients.pop(client_id, None)

    return app.response_class(stream(), mimetype="text/event-stream",
                               headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── 兼容旧接口 ──

@app.route("/api/contracts", methods=["GET"])
def list_contracts():
    """列出合同记录（兼容旧接口）"""
    return api_contracts_list()


# ═══════════════════════════════════════════════════════
# 图片生成（长文转图片，用于微信发送）
# ═══════════════════════════════════════════════════════

@app.route("/api/text-to-image", methods=["POST"])
@api_handler
def text_to_image():
    """将文字内容生成图片（微信排版用）
    
    Body: {"title": "标题", "lines": ["行1", "行2"], "footer": "底部文字"}
    """
    data = request.json or {}
    title = ParamValidator.optional(data, "title", "", str)
    lines = ParamValidator.required(data, "lines", list)
    footer = ParamValidator.optional(data, "footer", "", str)

    if not lines:
        raise ValueError("lines 不能为空列表")

    try:
        from sender.image_generator import create_message_image
        image_path = create_message_image(title=title, content_lines=lines, footer=footer)
        return success_response({
            "image_path": image_path,
            "title": title,
            "lines_count": len(lines)
        }, "图片生成成功")
    except ImportError:
        raise ValueError("image_generator 模块不可用")


# ═══════════════════════════════════════════════════════
# 综合操作（一键发图：选图 + 发送 + 记录）
# ═══════════════════════════════════════════════════════

@app.route("/api/send-product-image", methods=["POST"])
@api_handler
def send_product_image():
    """一键发送产品图片（选图 + 发送 + 记录）
    
    Body: {"contact": "联系人", "model": "型号", "session_id": "会话ID"}
    """
    data = request.json or {}
    contact = ParamValidator.required(data, "contact", str)
    model = ParamValidator.required(data, "model", str)
    session_id = ParamValidator.optional(data, "session_id", "", str)
    
    log(f"[API] send_product_image 被调用 - 型号: {model}, 联系人: {contact}")

    # 选图
    image_path = pick_best_image(model, session_id)
    log(f"[API] send_product_image 选图结果 - 型号: {model}, 找到图片: {bool(image_path)}")
    
    if not image_path:
        log(f"[API] send_product_image 图片不存在，准备通知资料员")
        # 通知资料员补充资料
        notified = notify_materials_staff(model, f"客户[{contact}]请求发送产品图片，但型号 {model} 缺少图片资料")
        
        error_msg = f"型号 {model} 无可用图片"
        if notified:
            error_msg += "，已通知资料员补充"
        
        log(f"[API] send_product_image 返回错误: {error_msg}")
        raise FileNotFoundError(error_msg)

    # 发送
    from sender.wechat_sender import send_image_safe
    result = send_image_safe(contact, image_path)
    
    if result.get("success"):
        if session_id:
            record_sent_image(session_id, model, image_path)
            log(f"[产品图] {model} -> {contact}: {os.path.basename(image_path)}")
        return success_response({
            "image_path": image_path,
            "model": model,
            "contact": contact,
            "session_id": session_id
        }, "产品图片发送成功")
    else:
        raise ValueError(result.get("error", "发送失败"))


# ═══════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════
# 合同审批页面（静态文件服务）
# ═══════════════════════════════════════════════════════

_CONTRACTS_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "web")


@app.route("/contracts")
@app.route("/contracts/")
def serve_contracts_page():
    """服务合同审批页面 HTML"""
    html_path = os.path.join(_CONTRACTS_WEB_DIR, "contracts.html")
    if not os.path.exists(html_path):
        return "contracts.html 不存在", 404
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/contracts.js")
def serve_contracts_js():
    """服务合同审批页面 JS"""
    js_path = os.path.join(_CONTRACTS_WEB_DIR, "contracts.js")
    if not os.path.exists(js_path):
        return "// JS文件缺失", 404, {"Content-Type": "application/javascript; charset=utf-8"}
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 替换模板变量
    content = content.replace("{{API_TOKEN}}", CLOUD_TOKEN or "")
    return content, 200, {"Content-Type": "application/javascript; charset=utf-8"}


@app.route("/contracts/images/<filename>")
def serve_contract_image(filename):
    """服务合同图片"""
    from config import CONTRACTS_DIR
    img_path = os.path.join(CONTRACTS_DIR, "images", filename)
    if not os.path.exists(img_path):
        return "图片不存在", 404
    ext = os.path.splitext(filename)[1].lower()
    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext.lstrip("."), "image/jpeg")
    return send_file(img_path, mimetype=ct)


# ═══════════════════════════════════════════════════════
# 客户画像审批页面（静态文件服务）
# ═══════════════════════════════════════════════════════

@app.route("/customers")
@app.route("/customers/")
def serve_customers_page():
    """服务客户画像审批页面 HTML"""
    html_path = os.path.join(_CONTRACTS_WEB_DIR, "customers.html")
    if not os.path.exists(html_path):
        return "customers.html 不存在", 404
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/contracts/diag")
@api_handler
def api_contracts_diag():
    """诊断接口：检查云端合同SSE连接状态"""
    return success_response({
        "cloud_server": CLOUD_SERVER,
        "sales_id": SALES_ID,
        "cloud_token_set": bool(CLOUD_TOKEN),
        "sse_enabled": bool(CLOUD_SERVER and SALES_ID),
        "message": "如果SSE已启用但收不到事件，请检查: 1) 云端合同agent_id是否匹配 2) 重启本地Claw重建连接"
    })


# ═══════════════════════════════════════════════════════
# 资料员管理页面
# ═══════════════════════════════════════════════════════

@app.route("/materials")
def materials_page():
    """资料员产品资料管理页面"""
    return send_file(os.path.join(BASE_DIR, "server", "web", "materials.html"))


# ═══════════════════════════════════════════════════════
# 云端合同回调（云端审批通过 → 本地下载PDF → 本地发送给客户）
# ═══════════════════════════════════════════════════════

@app.route("/api/contracts/callback", methods=["POST"])
def contract_callback():
    """接收云端合同审批结果回调（主入口）- 优化版，减少延迟

    Body: {
        "contract_id": "CT202604281056",
        "action": "approved",       // 或 "rejected"
        "approver": "滕成",
        "pdf_url": "https://...",   // 审批后PDF地址（云端可能编辑过）
        "customer_contact": "客户微信昵称"  // 可选
    }
    """
    data = request.json or {}
    contract_id = data.get("contract_id", "")
    action = data.get("action", "")

    if not contract_id or not action:
        return jsonify({"success": False, "error": "缺少 contract_id 或 action"}), 400

    if action == "approved":
        pdf_url = data.get("pdf_url", "")
        approver = data.get("approver", "云端审批")
        customer_contact = data.get("customer_contact", "")

        def _handle():
            start_time = datetime.now()
            try:
                contracts = load_contracts()
                if contract_id not in contracts:
                    log(f"[回调] 合同 {contract_id} 不存在")
                    return

                contract = contracts[contract_id]
                target = customer_contact or contract.customer_nickname or contract.order.company_name

                # 1. 优先从云端下载PDF（云端可能编辑过，本地版本已过时）
                pdf_path = ""
                if pdf_url:
                    pdf_path = _download_cloud_pdf(contract_id, pdf_url)
                    if pdf_path:
                        contract.pdf_path = pdf_path
                        contracts[contract_id] = contract
                        save_contracts(contracts)

                # 2. 兜底用本地PDF
                if not pdf_path:
                    pdf_path = contract.pdf_path

                if not pdf_path or not os.path.exists(pdf_path):
                    log(f"[回调] PDF不存在，无法发送: {contract_id}")
                    return

                download_time = (datetime.now() - start_time).total_seconds()
                log(f"[回调] PDF下载耗时: {download_time:.2f}s")

                # 3. 更新状态 + 发送
                contract.status = ContractStatus.APPROVED
                contract.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                contract.approved_by = approver
                contracts[contract_id] = contract
                save_contracts(contracts)

                from contract.contract_generator import send_contract
                send_ok = send_contract(contract_id)
                total_time = (datetime.now() - start_time).total_seconds()
                log(f"[回调] 合同 {contract_id} → {target}，发送{'成功' if send_ok else '失败'}，总耗时: {total_time:.2f}s")
                _notify_contract_sse()

            except Exception as e:
                log(f"[回调] 处理异常 {contract_id}: {e}")
                traceback.print_exc()

        threading.Thread(target=_handle, daemon=True, name=f"callback-{contract_id}").start()
        return jsonify({"success": True, "message": "正在处理"})

    elif action == "rejected":
        contracts = load_contracts()
        if contract_id in contracts:
            contract = contracts[contract_id]
            contract.status = ContractStatus.REJECTED
            contract.reject_reason = data.get("reason", "")
            contracts[contract_id] = contract
            save_contracts(contracts)
        log(f"[回调] 合同 {contract_id} 被拒绝")
        _notify_contract_sse()
        return jsonify({"success": True, "action": "rejected"})

    return jsonify({"success": False, "error": f"未知 action: {action}"}), 400


@app.route("/api/contracts/cloud-callback", methods=["POST"])
def cloud_contract_callback():
    """云端审批回调（兼容入口，逻辑同上）"""
    return contract_callback()


def _fetch_contract_from_cloud(contract_id: str) -> Optional['Contract']:
    """从云端获取合同数据并创建本地合同对象
    
    返回:
        Contract: 合同对象，获取失败返回 None
    """
    try:
        if not CLOUD_SERVER:
            log(f"[云端同步] 未配置云端服务器")
            return None
        
        url = f"{CLOUD_SERVER.rstrip('/')}/api/contracts/detail/{contract_id}"
        headers = {}
        if CLOUD_TOKEN:
            headers["Authorization"] = f"Bearer {CLOUD_TOKEN}"
        
        log(f"[云端同步] 获取合同数据: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            log(f"[云端同步] 获取合同失败: {resp.status_code}")
            return None
        
        data = resp.json()
        contract_data = data.get("contract", {})
        
        if not contract_data:
            log(f"[云端同步] 合同数据为空")
            return None
        
        # 创建本地合同对象
        from contract.contract_generator import Contract, OrderInfo, ContractStatus
        
        order_data = contract_data.get("order", {})
        order = OrderInfo(
            customer_name=order_data.get("customer_name", ""),
            customer_contact=order_data.get("customer_contact", ""),
            customer_phone=order_data.get("customer_phone", ""),
            customer_address=order_data.get("customer_address", ""),
            products=order_data.get("products", []),
            order_no=order_data.get("order_no", contract_id),
            order_date=order_data.get("order_date", ""),
            delivery_date=order_data.get("delivery_date", ""),
            payment_terms=order_data.get("payment_terms", ""),
            voltage=order_data.get("voltage", "220V/50Hz"),
            plug_type=order_data.get("plug_type", "国标/欧规/美规"),
            shipping_country=order_data.get("shipping_country", ""),
            notes=order_data.get("notes", ""),
        )
        
        contract = Contract(
            id=contract_id,
            session_id=contract_data.get("session_id", ""),
            customer_wxid=contract_data.get("customer_wxid", ""),
            customer_nickname=contract_data.get("customer_nickname", ""),
            agent_id=contract_data.get("agent_id", ""),
            order=order,
            status=ContractStatus.APPROVED,  # 云端已审批
            created_at=contract_data.get("created_at", ""),
            approved_at=contract_data.get("approved_at", ""),
            approved_by=contract_data.get("approved_by", "云端审批"),
            pdf_path="",  # 稍后下载
            xlsx_path="",
        )
        
        log(f"[云端同步] 成功获取合同: {contract_id}, 客户: {contract.customer_nickname}")
        return contract
        
    except Exception as e:
        log(f"[云端同步] 获取合同异常: {e}")
        return None


def _download_cloud_pdf(contract_id: str, pdf_url: str, max_retries: int = 15) -> str:
    """从云端下载PDF合同文件（带重试，应对云端异步生成）
    
    返回:
        str: 本地PDF文件路径，下载失败返回空字符串
    """
    import requests as req
    import time
    from contract.contract_generator import APPROVED_DIR
    
    # 构建本地保存路径
    pdf_filename = f"合同_{contract_id}_云端审批.pdf"
    local_path = os.path.join(APPROVED_DIR, pdf_filename)
    
    headers = {}
    if CLOUD_TOKEN:
        headers["Authorization"] = f"Bearer {CLOUD_TOKEN}"
    
    # 增加连接池和重试配置
    session = req.Session()
    adapter = req.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=10,
        max_retries=3
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    for attempt in range(max_retries):
        try:
            log(f"[下载PDF] 尝试 {attempt+1}/{max_retries}: {pdf_url}")
            # 增加超时时间: 连接30秒，读取120秒
            resp = session.get(
                pdf_url, 
                headers=headers, 
                timeout=(30, 120),  # (连接超时, 读取超时)
                stream=True
            )
            
            # 202 = PDF正在生成中
            if resp.status_code == 202:
                # 递增等待时间: 5, 8, 11, 14, 17, 20... 最多30秒
                wait_time = min(5 + attempt * 3, 30)
                log(f"[下载PDF] 云端PDF正在生成(202)，等待{wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            
            # 404 = PDF不存在，可能是生成失败或尚未开始
            if resp.status_code == 404:
                wait_time = min(3 + attempt * 2, 10)
                log(f"[下载PDF] PDF不存在(404)，等待{wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            
            # 500系列错误 = 服务器内部错误
            if resp.status_code >= 500:
                wait_time = min(5 + attempt * 2, 20)
                log(f"[下载PDF] 服务器错误({resp.status_code})，等待{wait_time}秒后重试...")
                time.sleep(wait_time)
                continue
            
            # 其他错误状态码
            if resp.status_code != 200:
                log(f"[下载PDF] 意外状态码: {resp.status_code}")
                resp.raise_for_status()
            
            # 保存文件
            total_size = 0
            with open(local_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            # 验证文件大小
            if total_size < 1024:  # 小于1KB可能是个错误页面
                log(f"[下载PDF] 警告: 文件过小({total_size}字节)，可能下载不完整")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            
            log(f"[下载PDF] 保存成功: {local_path} ({total_size}字节)")
            session.close()
            return local_path
            
        except req.exceptions.ConnectTimeout:
            log(f"[下载PDF] 尝试 {attempt+1} 连接超时")
            if attempt < max_retries - 1:
                wait_time = min(5 + attempt * 2, 15)
                log(f"[下载PDF] 等待{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                log(f"[下载PDF] 所有重试失败，连接超时")
                
        except req.exceptions.ReadTimeout:
            log(f"[下载PDF] 尝试 {attempt+1} 读取超时，云端生成可能较慢")
            if attempt < max_retries - 1:
                wait_time = min(5 + attempt * 2, 20)
                log(f"[下载PDF] 等待{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                log(f"[下载PDF] 所有重试失败，读取超时")
                
        except req.exceptions.ConnectionError as e:
            log(f"[下载PDF] 尝试 {attempt+1} 连接错误: {e}")
            if attempt < max_retries - 1:
                wait_time = min(3 + attempt, 10)
                time.sleep(wait_time)
            else:
                log(f"[下载PDF] 所有重试失败，连接错误")
                
        except Exception as e:
            log(f"[下载PDF] 尝试 {attempt+1} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                log(f"[下载PDF] 所有重试失败: {e}")
    
    session.close()
    return ""


# ── 云端代理（保留：部分操作仍可代理到云端）──

@app.route("/api/contracts/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy_contracts(subpath):
    """代理合同API请求到云端服务器（未在本地实现的接口走此代理）"""
    if not CLOUD_SERVER:
        return jsonify({"error": "合同服务器未配置，且本地接口未覆盖此路径"}), 503

    try:
        import requests as req
        url = f"{CLOUD_SERVER}/api/contracts/{subpath}"
        headers = {"Authorization": f"Bearer {CLOUD_TOKEN}"}

        # 转发查询参数
        if request.query_string:
            url += "?" + request.query_string.decode("utf-8")

        # 转发请求体
        body = None
        if request.method in ("POST", "PUT"):
            body = request.get_data()
            headers["Content-Type"] = request.content_type or "application/json"

        log(f"[合同代理] {request.method} /api/contracts/{subpath} → 云端")
        resp = req.request(
            request.method, url, headers=headers, data=body,
            timeout=120,
        )
        log(f"[合同代理] 云端响应: HTTP {resp.status_code} ({len(resp.content)} bytes)")
        return (resp.content, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "application/json")})
    except Exception as e:
        log(f"[合同代理] 请求失败: {e}")
        return jsonify({"error": f"云端请求失败: {e}"}), 502


# ═══════════════════════════════════════════════════════
# 云端合同 SSE 订阅（替代 HTTP 回调）
# ═══════════════════════════════════════════════════════

def _subscribe_contract_sse():
    """订阅云端合同审批事件 SSE（使用原生socket，与AI助手相同）"""
    import socket
    import time
    import threading
    import re

    if not CLOUD_SERVER:
        log("[合同SSE] 未配置CLOUD_SERVER，跳过订阅")
        return

    def _run():
        auth = f"Bearer {CLOUD_TOKEN}" if CLOUD_TOKEN else ""

        try:
            m = re.match(r'http://([^:]+):(\d+)', CLOUD_SERVER)
            if not m:
                log(f"[合同SSE] CLOUD_SERVER格式错误: {CLOUD_SERVER}")
                return
            host, port = m.group(1), int(m.group(2))
        except Exception as e:
            log(f"[合同SSE] 解析CLOUD_SERVER失败: {e}")
            return

        log(f"[合同SSE] 正在连接: {host}:{port}")

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((host, port))

            req = (
                f"GET /api/contracts/agent-events?agent={SALES_ID} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Accept: text/event-stream\r\n"
                f"Cache-Control: no-cache\r\n"
                f"Connection: keep-alive\r\n"
                f"Authorization: {auth}\r\n"
                f"\r\n"
            )
            sock.sendall(req.encode())
            log(f"[合同SSE] 已连接 (SALES_ID={SALES_ID})")

            header_data = b""
            while b"\r\n\r\n" not in header_data:
                chunk = sock.recv(4096)
                if not chunk:
                    raise Exception("服务器关闭连接")
                header_data += chunk
            body_data = header_data[header_data.index(b"\r\n\r\n") + 4:]

            while True:
                try:
                    chunk = sock.recv(8192)
                    if not chunk:
                        log("[合同SSE] 连接已关闭")
                        break
                    body_data += chunk
                    text = body_data.decode("utf-8", errors="replace")
                    body_data = b""

                    for line in text.split('\n'):
                        line = line.strip()
                        if line.startswith('data:'):
                            raw_json = line[5:].strip()
                            # 跳过心跳和连接确认
                            if raw_json == "[DONE]" or raw_json == "":
                                continue
                            if '"type":"heartbeat"' in raw_json:
                                continue
                            if '"type":"connected"' in raw_json:
                                continue
                            try:
                                data_map = json.loads(raw_json)
                                _handle_contract_event(data_map)
                            except json.JSONDecodeError:
                                log(f"[合同SSE] JSON解析失败: {raw_json[:80]}")

                    time.sleep(0.1)

                except socket.timeout:
                    continue

        except Exception as e:
            log(f"[合同SSE] 连接失败: {e}，5秒后重试...")
            time.sleep(5)
            threading.Thread(target=_run, daemon=True).start()
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    threading.Thread(target=_run, daemon=True).start()


# 已处理的合同事件记录（防重）
_processed_contract_events: set = set()


def _handle_contract_event(event: dict):
    """处理云端合同事件"""
    contract_id = event.get("contract_id", "")
    action = event.get("action", "")
    agent_id = event.get("agent_id", "")

    # 跳过空事件（如心跳包）
    if not contract_id or not action:
        return

    # 只处理当前业务员的合同
    if agent_id and agent_id != SALES_ID:
        return
    
    # 防重检查：同一个合同同一个动作只处理一次
    event_key = f"{contract_id}:{action}"
    if event_key in _processed_contract_events:
        log(f"[合同SSE] 跳过重复事件: {contract_id} -> {action}")
        return
    
    # 记录已处理的事件（保留最近100条）
    _processed_contract_events.add(event_key)
    if len(_processed_contract_events) > 100:
        # 清理旧记录
        _processed_contract_events.clear()
        _processed_contract_events.add(event_key)

    log(f"[合同SSE] 处理: {contract_id} -> {action}")

    if action == "approved":
        pdf_url = event.get("pdf_url", "")
        customer_wxid = event.get("customer_wxid", "")
        customer_nickname = event.get("customer_nickname", "")

        # 后台线程处理发送
        threading.Thread(
            target=_send_approved_contract,
            args=(contract_id, pdf_url, customer_wxid, customer_nickname),
            daemon=True,
            name=f"send-contract-{contract_id}"
        ).start()

    elif action == "rejected":
        # 更新本地合同状态为拒绝
        try:
            contracts = load_contracts()
            if contract_id in contracts:
                contract = contracts[contract_id]
                contract.status = ContractStatus.REJECTED
                contract.reject_reason = event.get("reason", "")
                contracts[contract_id] = contract
                save_contracts(contracts)
                log(f"[合同SSE] 合同 {contract_id} 已标记为拒绝")
                _notify_contract_sse()
        except Exception as e:
            log(f"[合同SSE] 更新拒绝状态失败: {e}")


# 正在发送中的合同（防止并发重复发送）
_sending_contracts: set = set()


def _send_approved_contract(contract_id: str, pdf_url: str, customer_wxid: str, customer_nickname: str):
    """发送已审批的合同给客户"""
    # 防并发重复发送检查
    if contract_id in _sending_contracts:
        log(f"[合同发送] 合同 {contract_id} 正在发送中，跳过")
        return
    
    _sending_contracts.add(contract_id)
    
    try:
        contracts = load_contracts()
        if contract_id not in contracts:
            log(f"[合同发送] 本地合同 {contract_id} 不存在，尝试从云端获取...")
            # 从云端获取合同数据
            contract = _fetch_contract_from_cloud(contract_id)
            if not contract:
                log(f"[合同发送] 云端合同 {contract_id} 也不存在，跳过")
                return
            # 保存到本地
            contracts[contract_id] = contract
            save_contracts(contracts)
            log(f"[合同发送] 已从云端同步合同 {contract_id} 到本地")
        else:
            contract = contracts[contract_id]
        target = customer_nickname or contract.customer_nickname or contract.order.company_name

        # 检查是否已经发送过（通过状态判断）- 暂时禁用，允许重复发送
        # if hasattr(contract, 'sent_at') and contract.sent_at:
        #     log(f"[合同发送] 合同 {contract_id} 已于 {contract.sent_at} 发送过，跳过")
        #     return

        # 1. 从云端下载PDF（云端可能编辑过）
        pdf_path = ""
        if pdf_url:
            # 补全URL
            if pdf_url.startswith("/"):
                pdf_url = f"{CLOUD_SERVER.rstrip('/')}{pdf_url}"
            pdf_path = _download_cloud_pdf(contract_id, pdf_url)
            if pdf_path:
                contract.pdf_path = pdf_path
                contracts[contract_id] = contract
                save_contracts(contracts)

        # 2. 兜底用本地PDF
        if not pdf_path:
            pdf_path = contract.pdf_path

        if not pdf_path or not os.path.exists(pdf_path):
            log(f"[合同发送] PDF不存在: {contract_id}")
            return

        # 3. 更新状态
        contract.status = ContractStatus.APPROVED
        contract.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        contract.approved_by = "云端审批"
        contracts[contract_id] = contract
        save_contracts(contracts)

        # 4. 发送合同
        from contract.contract_generator import send_contract
        # 传入已加载的合同字典，避免重复加载和保存
        send_ok = send_contract(contract_id, contracts)
        
        # 记录发送时间（防止重复发送）
        if send_ok:
            contract.sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            contracts[contract_id] = contract
            save_contracts(contracts)
        
        log(f"[合同发送] {contract_id} -> {target}，{'成功' if send_ok else '失败'}")
        _notify_contract_sse()

    except Exception as e:
        log(f"[合同发送] 异常 {contract_id}: {e}")
        traceback.print_exc()
    finally:
        # 移除发送标记
        _sending_contracts.discard(contract_id)


# ═══════════════════════════════════════════════════════
# 向量记忆系统
# ═══════════════════════════════════════════════════════

_vector_memory = None

def get_vector_memory():
    """获取向量记忆实例（懒加载）"""
    global _vector_memory
    if _vector_memory is None:
        try:
            from vector_memory import VectorMemory
            _vector_memory = VectorMemory()
            log("[向量记忆] 初始化成功")
        except Exception as e:
            log(f"[向量记忆] 初始化失败: {e}")
            _vector_memory = None
    return _vector_memory


@app.route("/api/memory/store", methods=["POST"])
@api_handler
def store_memory():
    """存储记忆
    
    Body: {
        "text": "记忆内容",
        "source": "微信-健康办公研究社",
        "type": "chat",
        "customer": "健康办公研究社"
    }
    """
    data = request.json or {}
    text = ParamValidator.required(data, "text", str)
    source = ParamValidator.optional(data, "source", "unknown", str)
    memory_type = ParamValidator.optional(data, "type", "chat", str)
    customer = ParamValidator.optional(data, "customer", "", str)
    
    memory = get_vector_memory()
    if not memory:
        raise ValueError("vector memory not available")
    
    memory_id = memory.store(text, source=source, memory_type=memory_type, customer=customer)
    return success_response({
        "id": memory_id,
        "text_preview": text[:100] + "..." if len(text) > 100 else text
    }, "记忆存储成功")


@app.route("/api/memory/search", methods=["POST"])
@api_handler
def search_memory():
    """语义搜索记忆
    
    Body: {
        "query": "查询内容",
        "top_k": 5,
        "customer": "健康办公研究社"  // 可选，按客户过滤
    }
    """
    data = request.json or {}
    query = ParamValidator.required(data, "query", str)
    top_k = ParamValidator.optional(data, "top_k", 5, int)
    customer = ParamValidator.optional(data, "customer", "", str)
    
    memory = get_vector_memory()
    if not memory:
        raise ValueError("vector memory not available")
    
    results = memory.search(query, top_k=top_k, filter_customer=customer)
    return success_response({
        "query": query,
        "results": results,
        "count": len(results),
        "filter_customer": customer
    })


@app.route("/api/memory/stats", methods=["GET"])
@api_handler
def memory_stats():
    """获取向量记忆统计信息"""
    memory = get_vector_memory()
    if not memory:
        raise ValueError("vector memory not available")
    
    stats = memory.stats()
    return success_response(stats)


# ═══════════════════════════════════════════════════════
# 客户画像自动推送到云端审批系统
# ═══════════════════════════════════════════════════════

# 自动推送配置
auto_sync_enabled = True  # 默认启用自动推送
auto_sync_interval = 300  # 自动推送间隔（秒），默认5分钟
auto_sync_cloud_server = "http://120.26.84.224:5032"  # 云端审批系统地址


def _auto_push_profiles_to_cloud():
    """自动推送本地客户画像到云端审批系统的后台任务"""
    import time
    import json
    import os

    last_push_time = 0

    # 立即执行一次推送（首次启动）
    try:
        if auto_sync_enabled:
            # 导入推送函数
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
            from core.customer_sync import (
                push_all_profiles_to_cloud,
                CLOUD_APPROVAL_SERVER
            )

            # 执行推送
            result = push_all_profiles_to_cloud(
                cloud_server=CLOUD_APPROVAL_SERVER,
                filter_complete=True  # 只推送完整数据
            )

            if result.get('success_count', 0) > 0:
                log(f"[AutoPush] 首次推送: {result.get('success_count')} 个客户")

            last_push_time = time.time()
    except Exception as e:
        log(f"[AutoPush] 推送异常: {e}")

    # 进入定时循环
    while True:
        try:
            if auto_sync_enabled:
                current_time = time.time()
                # 达到间隔时间时推送
                if current_time - last_push_time >= auto_sync_interval:
                    # 导入推送函数
                    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
                    from core.customer_sync import (
                        push_all_profiles_to_cloud,
                        CLOUD_APPROVAL_SERVER
                    )

                    # 执行推送
                    result = push_all_profiles_to_cloud(
                        cloud_server=CLOUD_APPROVAL_SERVER,
                        filter_complete=True  # 只推送完整数据
                    )

                    if result.get('success_count', 0) > 0:
                        log(f"[AutoPush] 定时推送: {result.get('success_count')} 个客户")

                    last_push_time = current_time

            # 每10秒检查一次状态
            for _ in range(10):
                time.sleep(1)

        except Exception as e:
            log(f"[AutoPush] 异常: {e}")
            time.sleep(10)


# ═══════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    # 简洁的启动信息
    log("[OK] API 服务启动完成")
    log(f"     地址: http://{API_HOST}:{API_PORT}")

    # 启动云端合同 SSE 订阅（如果配置了云端服务器）
    if CLOUD_SERVER and SALES_ID:
        threading.Thread(target=_subscribe_contract_sse, daemon=True, name="contract-sse").start()
        log(f"[OK] 合同SSE订阅已启动 ({SALES_ID})")

    # 启动云端同步客户端（WebSocket版本，连接到云端同步服务器）
    if CLOUD_SYNC_ENABLED and CloudSyncWebSocketClient:
        cloud_ws_url = os.environ.get("CLOUD_WS_URL", "ws://120.26.84.224:5033")
        cloud_file_url = os.environ.get("CLOUD_FILE_URL", "http://120.26.84.224:5032")

        if cloud_ws_url:
            server_id = SALES_ID or os.environ.get("COMPUTERNAME", "local_unknown")
            cloud_sync_client = CloudSyncWebSocketClient(
                cloud_ws_url=cloud_ws_url,
                cloud_file_url=cloud_file_url,
                server_id=server_id
            )
            cloud_sync_client.start()
            log(f"[OK] 云端同步已启动 ({server_id})")

    # 启动客户画像自动推送服务
    auto_push_thread = threading.Thread(target=_auto_push_profiles_to_cloud, daemon=True, name="auto-push-profiles")
    auto_push_thread.start()
    log("[OK] 自动推送服务已启动")

    app.run(host=API_HOST, port=API_PORT, debug=False)
