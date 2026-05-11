"""
产品资料管理 API 模块
提供产品图片的云端存储和管理功能
"""
import os
import re
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, quote

# ═══════════════════════════════════════════════════════
# 日志工具 - 统一使用 core.config.log
# ═══════════════════════════════════════════════════════
try:
    from core.config import log
except ImportError:
    # 兜底日志函数
    def log(msg, tag="材料"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{tag}] {msg}", flush=True)

# 导入 SSE 服务
try:
    from sse_service import (
        notify_product_created, notify_product_deleted,
        notify_image_uploaded, notify_image_deleted,
        handle_sse_request
    )
    SSE_ENABLED = True
except ImportError:
    SSE_ENABLED = False
    notify_product_created = lambda *args, **kwargs: None
    notify_product_deleted = lambda *args, **kwargs: None
    notify_image_uploaded = lambda *args, **kwargs: None
    notify_image_deleted = lambda *args, **kwargs: None

# 导入知识库 API
try:
    from knowledge_api import handle_knowledge_request
    KNOWLEDGE_ENABLED = True
except ImportError:
    KNOWLEDGE_ENABLED = False
    handle_knowledge_request = lambda *args: False

# 配置
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PRODUCT_IMAGES_DIR = os.path.join(BASE_DIR, "assets", "images")
os.makedirs(PRODUCT_IMAGES_DIR, exist_ok=True)


def _paginate_data(data, page, page_size):
    """分页处理数据"""
    total = len(data)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    return {
        'data': data[start:end],
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages
        }
    }


def handle_request(handler, method, path):
    """处理产品资料管理 API 请求
    
    Args:
        handler: HTTPRequestHandler 实例
        method: HTTP 方法 (GET, POST, DELETE)
        path: 请求路径
        
    Returns:
        bool: 是否处理了该请求
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(path)
    query_params = parse_qs(parsed.query)
    
    # SSE 请求处理
    if SSE_ENABLED and handle_sse_request(handler, path):
        return True
    
    # 知识库 API 请求处理
    if KNOWLEDGE_ENABLED and handle_knowledge_request(handler, method, path):
        return True
    
    # 分页参数
    try:
        page = int(query_params.get('page', [1])[0])
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = int(query_params.get('page_size', [12])[0])
    except (ValueError, TypeError):
        page_size = 12
    page_size = min(page_size, 100)
    
    # GET 请求
    if method == "GET":
        # 获取统计信息
        if parsed.path == "/api/materials/stats":
            _handle_get_stats(handler)
            return True
        
        # 获取所有产品列表（带状态分类）
        if parsed.path == "/api/materials/products":
            status_filter = query_params.get('status', ['all'])[0]
            search_query = query_params.get('q', [''])[0].strip().lower()
            _handle_get_products(handler, page, page_size, status_filter, search_query)
            return True
        
        # 获取单个产品图片列表
        if parsed.path.startswith("/api/materials/products/") and parsed.path.endswith("/images"):
            model = parsed.path.split("/")[4]
            # URL 解码 model 名称
            from urllib.parse import unquote
            model = unquote(model)
            _handle_get_product_images(handler, model, page, page_size)
            return True
        
        # 获取单个产品图片（静态文件）
        if path.startswith("/assets/images/"):
            _handle_serve_product_image(handler, path)
            return True
    
    # POST 请求
    if method == "POST":
        # 创建新产品
        if parsed.path == "/api/materials/products":
            _handle_create_product(handler)
            return True
        
        # 上传产品图片
        if parsed.path.startswith("/api/materials/products/") and parsed.path.endswith("/images/upload"):
            model = parsed.path.split("/")[4]
            from urllib.parse import unquote
            model = unquote(model)
            _handle_upload_product_image(handler, model)
            return True
        
        # 重命名产品（修改型号）
        if parsed.path.startswith("/api/materials/products/") and parsed.path.endswith("/rename"):
            model = parsed.path.split("/")[4]
            from urllib.parse import unquote
            model = unquote(model)
            _handle_rename_product(handler, model)
            return True
        
        # 重命名产品图片
        if parsed.path.startswith("/api/materials/products/") and parsed.path.endswith("/images/rename"):
            model = parsed.path.split("/")[4]
            from urllib.parse import unquote
            model = unquote(model)
            _handle_rename_product_image(handler, model)
            return True

    # DELETE 请求
    if method == "DELETE":
        from urllib.parse import unquote
        log(f"DELETE request: path={parsed.path}, query={query_params}", "DEBUG")

        # 删除产品
        path_parts = parsed.path.split("/")
        if parsed.path.startswith("/api/materials/products/") and len(path_parts) == 5 and path_parts[4]:
            model = unquote(path_parts[4])
            _handle_delete_product(handler, model)
            return True

        # 删除产品图片
        # 路径格式: /api/materials/products/{model}/images?filename=xxx
        if parsed.path.startswith("/api/materials/products/") and "/images" in parsed.path:
            parts = parsed.path.split("/")
            if len(parts) >= 6 and parts[5] == "images":
                model = unquote(parts[4])
                filename = query_params.get('filename', [None])[0]
                log(f"Delete image: model={model}, filename={filename}", "DEBUG")
                if filename:
                    _handle_delete_product_image(handler, model, filename)
                    return True
    
    return False


def _send_json(handler, data, status=200):
    """发送 JSON 响应"""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def _handle_get_stats(handler):
    """获取统计信息"""
    try:
        products = []
        complete = 0
        needs_more = 0
        missing = 0
        
        for folder in Path(PRODUCT_IMAGES_DIR).iterdir():
            if folder.is_dir() and not folder.name.startswith("."):
                model = folder.name
                images = []
                for f in folder.iterdir():
                    if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                        images.append(f.name)
                
                # 根据图片数量分类
                if len(images) == 0:
                    missing += 1
                elif len(images) < 5:
                    needs_more += 1
                else:
                    complete += 1
                
                products.append(model)
        
        _send_json(handler, {
            "success": True,
            "data": {
                "total": len(products),
                "complete": complete,
                "needs_more": needs_more,
                "missing": missing
            }
        })
    except Exception as e:
        log(f"获取统计信息失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_get_products(handler, page, page_size, status_filter='all', search_query=''):
    """获取所有产品列表（带状态分类和搜索过滤）"""
    try:
        products = []
        
        for folder in Path(PRODUCT_IMAGES_DIR).iterdir():
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            
            model = folder.name
            
            # 搜索过滤：如果有搜索词，只保留匹配的型号
            if search_query and search_query not in model.lower():
                continue
            
            images = []
            for f in folder.iterdir():
                if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                    # 对文件名进行URL编码，避免特殊字符导致的问题
                    encoded_filename = quote(f.name, safe='')
                    images.append({
                        "filename": f.name,
                        "url": f"/assets/images/{model}/{encoded_filename}",
                        "size": f.stat().st_size
                    })
            
            # 确定状态
            if len(images) == 0:
                status = "missing"
                status_text = "缺少图片"
            elif len(images) < 3:
                status = "needs-more"
                status_text = "需要补充"
            else:
                status = "complete"
                status_text = "资料完整"
            
            # 根据状态筛选
            if status_filter != 'all' and status != status_filter:
                continue
            
            products.append({
                "model": model,
                "count": len(images),
                "images": images[:5],  # 只返回前5张预览
                "status": status,
                "status_text": status_text
            })
        
        # 按型号排序
        products.sort(key=lambda x: x["model"])
        
        # 分页
        result = _paginate_data(products, page, page_size)
        
        _send_json(handler, {
            "success": True,
            "data": result
        })
    except Exception as e:
        log(f"获取产品列表失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_get_product_images(handler, model, page, page_size):
    """获取单个产品图片列表"""
    try:
        product_dir = Path(PRODUCT_IMAGES_DIR) / model
        
        # 如果产品目录不存在，返回空数组而不是错误
        if not product_dir.exists():
            _send_json(handler, {
                "success": True,
                "data": {
                    "data": [],
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": 0,
                        "total_pages": 1
                    }
                }
            })
            return
        
        images = []
        for f in sorted(product_dir.iterdir()):
            if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                # 对文件名进行URL编码，避免特殊字符导致的问题
                # safe='/' 保留斜杠不编码
                encoded_filename = quote(f.name, safe='/')
                images.append({
                    "filename": f.name,
                    "url": f"/assets/images/{model}/{encoded_filename}",
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })
        
        # 分页
        result = _paginate_data(images, page, page_size)
        
        _send_json(handler, {
            "success": True,
            "data": result
        })
    except Exception as e:
        log(f"获取产品图片失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_serve_product_image(handler, path):
    """提供产品图片文件"""
    try:
        # 解码URL（处理多次编码的情况）
        decoded_path = path
        for _ in range(3):  # 最多解码3次
            new_path = unquote(decoded_path)
            if new_path == decoded_path:
                break
            decoded_path = new_path
        
        # 移除 /assets/images/ 前缀
        relative_path = decoded_path.replace("/assets/images/", "").lstrip('/')
        
        # 安全检查：确保路径在图片目录内
        requested_path = Path(PRODUCT_IMAGES_DIR) / relative_path
        requested_path = requested_path.resolve()
        
        log(f"请求图片: {relative_path}", "IMAGE")
        
        # 验证路径
        if not str(requested_path).startswith(str(Path(PRODUCT_IMAGES_DIR).resolve())):
            log(f"403 禁止访问: {requested_path}", "IMAGE")
            handler.send_response(403)
            handler.end_headers()
            return
        
        if not requested_path.exists():
            log(f"404 文件不存在: {requested_path}", "IMAGE")
            handler.send_response(404)
            handler.end_headers()
            return

        # 发送文件
        import mimetypes
        content_type, _ = mimetypes.guess_type(str(requested_path))
        if not content_type:
            content_type = 'application/octet-stream'

        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "public, max-age=86400")
        handler.end_headers()

        with open(requested_path, 'rb') as f:
            handler.wfile.write(f.read())

    except Exception as e:
        log(f"提供图片失败: {e}", "ERROR")
        handler.send_response(500)
        handler.end_headers()


def _handle_create_product(handler):
    """创建新产品"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        data = json.loads(body)
        model = data.get('model', '').strip().upper()

        if not model:
            _send_json(handler, {"success": False, "error": "产品型号不能为空"}, 400)
            return

        # 安全检查
        if ".." in model or "/" in model or "\\" in model or "<" in model or ">" in model:
            _send_json(handler, {"success": False, "error": "非法产品型号"}, 400)
            return

        # 创建产品目录
        product_dir = Path(PRODUCT_IMAGES_DIR) / model
        if product_dir.exists():
            _send_json(handler, {"success": False, "error": "产品已存在"}, 400)
            return

        product_dir.mkdir(parents=True, exist_ok=True)
        
        # SSE 通知
        notify_product_created(model, {"path": str(product_dir)})

        _send_json(handler, {
            "success": True,
            "data": {
                "model": model,
                "path": str(product_dir)
            },
            "message": "产品创建成功"
        })
    except Exception as e:
        log(f"创建产品失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_delete_product(handler, model):
    """删除产品"""
    try:
        if not model:
            _send_json(handler, {"success": False, "error": "产品型号不能为空"}, 400)
            return

        # 安全检查
        if ".." in model or "/" in model or "\\" in model:
            _send_json(handler, {"success": False, "error": "非法产品型号"}, 400)
            return

        product_dir = Path(PRODUCT_IMAGES_DIR) / model

        if not product_dir.exists():
            _send_json(handler, {"success": False, "error": "产品不存在"}, 404)
            return

        # 移动到回收站
        trash_dir = Path(PRODUCT_IMAGES_DIR) / ".trash" / model
        trash_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_path = trash_dir / f"{model}.deleted.{timestamp}"

        shutil.move(str(product_dir), str(trash_path))
        
        # SSE 通知
        notify_product_deleted(model, {"trash_path": str(trash_path)})

        _send_json(handler, {
            "success": True,
            "data": {
                "model": model,
                "trash_path": str(trash_path)
            },
            "message": "产品已删除"
        })
    except Exception as e:
        log(f"删除产品失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_upload_product_image(handler, model):
    """上传产品图片"""
    try:
        # 安全检查
        if ".." in model or "/" in model or "\\" in model:
            _send_json(handler, {"success": False, "error": "非法产品型号"}, 400)
            return

        # 获取内容类型
        content_type = handler.headers.get('Content-Type', '')
        
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            _send_json(handler, {"success": False, "error": "没有上传文件"}, 400)
            return
        
        body = handler.rfile.read(content_length)
        
        # 解析 multipart/form-data
        if 'multipart/form-data' in content_type:
            # 获取 boundary
            boundary = content_type.split('boundary=')[1].strip()
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            
            # 解析表单数据
            parts = _parse_multipart_form(body, boundary)
            
            # 获取文件数据
            file_data = None
            filename = None
            description = ""
            
            for part in parts:
                if part.get('filename'):
                    file_data = part['data']
                    filename = part['filename']
                elif part.get('name') == 'description':
                    description = part['data'].decode('utf-8', errors='ignore')
            
            if not file_data:
                _send_json(handler, {"success": False, "error": "没有找到文件"}, 400)
                return
        else:
            _send_json(handler, {"success": False, "error": "不支持的Content-Type"}, 400)
            return

        # 检查文件类型
        allowed_ext = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        ext = Path(filename).suffix.lower()
        if ext not in allowed_ext:
            _send_json(handler, {"success": False, "error": f"不支持的文件类型: {ext}"}, 400)
            return

        # 创建产品目录
        product_dir = Path(PRODUCT_IMAGES_DIR) / model
        product_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if description:
            safe_desc = "".join(c if c.isalnum() or c in "_-" else "_" for c in description)[:20]
            new_filename = f"{model}_{safe_desc}_{timestamp}{ext}"
        else:
            new_filename = f"{model}_{timestamp}{ext}"

        # 保存文件
        file_path = product_dir / new_filename
        with open(file_path, "wb") as f:
            f.write(file_data if isinstance(file_data, bytes) else file_data.encode())
        
        # SSE 通知
        file_size = len(file_data) if isinstance(file_data, bytes) else len(file_data.encode())
        notify_image_uploaded(model, new_filename, {"size": file_size})

        _send_json(handler, {
            "success": True,
            "data": {
                "model": model,
                "filename": new_filename,
                "path": str(file_path),
                "url": f"/assets/images/{model}/{new_filename}",
                "size": file_size
            },
            "message": "图片上传成功"
        })
    except Exception as e:
        log(f"上传图片失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_delete_product_image(handler, model, filename):
    """删除产品图片"""
    log(f"开始删除图片: 产品={model}, 文件={filename}", "图片删除")
    try:
        # 安全检查
        if ".." in model or "/" in model or "\\" in model:
            log(f"非法产品型号: {model}", "图片删除")
            _send_json(handler, {"success": False, "error": "非法产品型号"}, 400)
            return
        
        if ".." in filename or "/" in filename or "\\" in filename:
            log(f"非法文件名: {filename}", "图片删除")
            _send_json(handler, {"success": False, "error": "非法文件名"}, 400)
            return

        product_dir = Path(PRODUCT_IMAGES_DIR) / model
        file_path = product_dir / filename

        # 检查文件是否存在
        if not file_path.exists():
            log(f"文件不存在: {file_path}", "图片删除")
            _send_json(handler, {"success": False, "error": "文件不存在"}, 404)
            return

        # 移动到回收站
        trash_dir = Path(PRODUCT_IMAGES_DIR) / ".trash" / model
        trash_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_name = f"{file_path.stem}.deleted.{timestamp}{file_path.suffix}"
        trash_path = trash_dir / trash_name

        shutil.move(str(file_path), str(trash_path))
        log(f"图片已移动到回收站: {trash_path}", "图片删除")
        
        # SSE 通知
        notify_image_deleted(model, filename, {"trash_path": str(trash_path)})

        _send_json(handler, {
            "success": True,
            "data": {
                "model": model,
                "filename": filename,
                "trash_path": str(trash_path)
            },
            "message": "图片已删除"
        })
        log(f"图片删除成功: {model}/{filename}", "图片删除")
    except Exception as e:
        log(f"图片删除失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_rename_product_image(handler, model):
    """重命名产品图片"""
    log(f"开始重命名图片: 产品={model}", "图片重命名")
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8')
        data = json.loads(body)
        
        old_filename = data.get('old_filename', '')
        new_filename = data.get('new_filename', '')
        
        log(f"重命名: {old_filename} -> {new_filename}", "图片重命名")
        
        # 安全检查
        if ".." in model or "/" in model or "\\" in model:
            _send_json(handler, {"success": False, "error": "非法产品型号"}, 400)
            return
        
        if ".." in old_filename or "/" in old_filename or "\\" in old_filename:
            _send_json(handler, {"success": False, "error": "非法旧文件名"}, 400)
            return
        
        if ".." in new_filename or "/" in new_filename or "\\" in new_filename:
            _send_json(handler, {"success": False, "error": "非法新文件名"}, 400)
            return
        
        # 确保新文件名有扩展名
        if not new_filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
            # 从旧文件名获取扩展名
            old_ext = Path(old_filename).suffix
            new_filename = new_filename + old_ext
        
        product_dir = Path(PRODUCT_IMAGES_DIR) / model
        old_path = product_dir / old_filename
        new_path = product_dir / new_filename
        
        # 检查旧文件是否存在
        if not old_path.exists():
            log(f"文件不存在: {old_path}", "图片重命名")
            _send_json(handler, {"success": False, "error": "文件不存在"}, 404)
            return
        
        # 检查新文件名是否已存在
        if new_path.exists():
            _send_json(handler, {"success": False, "error": "新文件名已存在"}, 400)
            return
        
        # 执行重命名
        shutil.move(str(old_path), str(new_path))
        log(f"图片重命名成功: {old_filename} -> {new_filename}", "图片重命名")
        
        _send_json(handler, {
            "success": True,
            "data": {
                "model": model,
                "old_filename": old_filename,
                "new_filename": new_filename
            },
            "message": "图片重命名成功"
        })
    except Exception as e:
        log(f"图片重命名失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _parse_multipart_form(body, boundary):
    """解析 multipart/form-data"""
    parts = []
    boundary_bytes = f"--{boundary}".encode()
    
    # 分割数据
    chunks = body.split(boundary_bytes)
    
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or chunk == b'--':
            continue
        
        # 分割头部和数据
        if b'\r\n\r\n' in chunk:
            headers_bytes, data = chunk.split(b'\r\n\r\n', 1)
            headers = headers_bytes.decode('utf-8', errors='ignore')
            
            # 解析 Content-Disposition
            part_info = {}
            if 'Content-Disposition:' in headers:
                cd_match = re.search(r'Content-Disposition: form-data; (.+)', headers, re.DOTALL)
                if cd_match:
                    cd_params = cd_match.group(1)
                    
                    # 提取 name
                    name_match = re.search(r'name="([^"]+)"', cd_params)
                    if name_match:
                        part_info['name'] = name_match.group(1)
                    
                    # 提取 filename
                    filename_match = re.search(r'filename="([^"]+)"', cd_params)
                    if filename_match:
                        part_info['filename'] = filename_match.group(1)
            
            # 移除末尾的换行
            if data.endswith(b'\r\n'):
                data = data[:-2]
            
            part_info['data'] = data
            parts.append(part_info)

    return parts


def _handle_rename_product(handler, old_model):
    """重命名产品（修改型号）"""
    log(f"开始重命名产品: {old_model}", "产品重命名")
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        data = json.loads(body)
        new_model = data.get('new_model', '').strip().upper()
        
        log(f"新型号: {new_model}", "产品重命名")

        if not old_model or not new_model:
            log(f"型号不能为空", "产品重命名")
            _send_json(handler, {"success": False, "error": "产品型号不能为空"}, 400)
            return

        # 安全检查
        if ".." in old_model or "/" in old_model or "\\" in old_model or "<" in old_model or ">" in old_model:
            log(f"非法原产品型号: {old_model}", "产品重命名")
            _send_json(handler, {"success": False, "error": "非法原产品型号"}, 400)
            return
        
        if ".." in new_model or "/" in new_model or "\\" in new_model or "<" in new_model or ">" in new_model:
            log(f"非法新产品型号: {new_model}", "产品重命名")
            _send_json(handler, {"success": False, "error": "非法新产品型号"}, 400)
            return

        # 检查原产品是否存在
        old_product_dir = Path(PRODUCT_IMAGES_DIR) / old_model
        if not old_product_dir.exists():
            log(f"原产品不存在: {old_model}", "产品重命名")
            _send_json(handler, {"success": False, "error": "原产品不存在"}, 404)
            return

        # 检查新产品是否已存在
        new_product_dir = Path(PRODUCT_IMAGES_DIR) / new_model
        if new_product_dir.exists():
            log(f"新产品型号已存在: {new_model}", "产品重命名")
            _send_json(handler, {"success": False, "error": "新产品型号已存在"}, 400)
            return

        # 重命名目录
        shutil.move(str(old_product_dir), str(new_product_dir))
        log(f"产品目录已重命名: {old_model} -> {new_model}", "产品重命名")
        
        # SSE 通知：删除旧产品，创建新产品
        notify_product_deleted(old_model, {"renamed_to": new_model})
        notify_product_created(new_model, {"renamed_from": old_model})

        _send_json(handler, {
            "success": True,
            "data": {
                "old_model": old_model,
                "new_model": new_model,
                "path": str(new_product_dir)
            },
            "message": "产品型号修改成功"
        })
        log(f"产品重命名成功: {old_model} -> {new_model}", "产品重命名")
    except Exception as e:
        log(f"产品重命名失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)

