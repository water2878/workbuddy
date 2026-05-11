"""
知识库管理 API 模块
提供产品知识库文件的云端管理功能
"""
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

# 导入 SSE 服务
try:
    from sse_service import (
        notify_knowledge_created, notify_knowledge_updated,
        notify_knowledge_deleted
    )
    SSE_ENABLED = True
except ImportError:
    SSE_ENABLED = False
    notify_knowledge_created = lambda *args, **kwargs: None
    notify_knowledge_updated = lambda *args, **kwargs: None
    notify_knowledge_deleted = lambda *args, **kwargs: None

# 配置
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
KNOWLEDGE_BASE_DIR = os.path.join(BASE_DIR, "assets", "products")
os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)


def _send_json(handler, data, status=200):
    """发送 JSON 响应"""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def handle_knowledge_request(handler, method, path):
    """处理知识库管理 API 请求
    
    Args:
        handler: HTTPRequestHandler 实例
        method: HTTP 方法
        path: 请求路径
        
    Returns:
        bool: 是否处理了该请求
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(path)
    
    # GET /api/materials/knowledge - 获取所有知识库文件列表
    if parsed.path == "/api/materials/knowledge" and method == "GET":
        _handle_get_knowledge_files(handler)
        return True
    
    # GET /api/materials/knowledge/<filename> - 获取单个文件内容
    if parsed.path.startswith("/api/materials/knowledge/") and method == "GET":
        filename = unquote(parsed.path.split("/")[4])
        _handle_get_knowledge_file(handler, filename)
        return True
    
    # POST /api/materials/knowledge - 创建新文件
    if parsed.path == "/api/materials/knowledge" and method == "POST":
        _handle_create_knowledge_file(handler)
        return True
    
    # POST /api/materials/knowledge/<filename> - 更新文件
    if parsed.path.startswith("/api/materials/knowledge/") and method == "POST":
        filename = unquote(parsed.path.split("/")[4])
        _handle_update_knowledge_file(handler, filename)
        return True
    
    # DELETE /api/materials/knowledge/<filename> - 删除文件
    if parsed.path.startswith("/api/materials/knowledge/") and method == "DELETE":
        filename = unquote(parsed.path.split("/")[4])
        _handle_delete_knowledge_file(handler, filename)
        return True
    
    return False


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


def _handle_get_knowledge_files(handler):
    """获取所有知识库文件列表"""
    try:
        from urllib.parse import urlparse, parse_qs
        import urllib.parse

        # 解析查询参数
        parsed = urlparse(handler.path)
        query_params = parse_qs(parsed.query)

        page = int(query_params.get('page', [1])[0])
        page_size = int(query_params.get('page_size', [12])[0])
        page_size = min(page_size, 100)

        files = []
        kb_dir = Path(KNOWLEDGE_BASE_DIR)

        if kb_dir.exists():
            for f in sorted(kb_dir.iterdir()):
                if f.is_file() and f.suffix.lower() == '.md':
                    stat = f.stat()
                    files.append({
                        "filename": f.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "is_main": "单品种知识库" in f.name
                    })

        # 分页
        result = _paginate_data(files, page, page_size)

        _send_json(handler, {
            "success": True,
            "data": result
        })
    except Exception as e:
        print(f"[ERROR] 获取知识库文件列表失败: {e}", flush=True)
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_get_knowledge_file(handler, filename):
    """获取单个知识库文件内容"""
    try:
        # 安全检查
        if ".." in filename or "/" in filename or "\\" in filename:
            _send_json(handler, {"success": False, "error": "非法文件名"}, 400)
            return
        
        # 确保是 .md 文件
        if not filename.endswith('.md'):
            filename += '.md'
        
        file_path = Path(KNOWLEDGE_BASE_DIR) / filename
        
        if not file_path.exists():
            _send_json(handler, {"success": False, "error": "文件不存在"}, 404)
            return
        
        content = file_path.read_text(encoding='utf-8')
        
        _send_json(handler, {
            "success": True,
            "data": {
                "filename": filename,
                "content": content,
                "size": len(content)
            }
        })
    except Exception as e:
        print(f"[ERROR] 获取知识库文件失败: {e}", flush=True)
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_create_knowledge_file(handler):
    """创建新知识库文件"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        data = json.loads(body)
        
        filename = data.get('filename', '').strip()
        content = data.get('content', '')
        
        if not filename:
            _send_json(handler, {"success": False, "error": "文件名不能为空"}, 400)
            return
        
        # 确保是 .md 文件
        if not filename.endswith('.md'):
            filename += '.md'
        
        # 安全检查
        if ".." in filename or "/" in filename or "\\" in filename:
            _send_json(handler, {"success": False, "error": "非法文件名"}, 400)
            return
        
        file_path = Path(KNOWLEDGE_BASE_DIR) / filename
        
        if file_path.exists():
            _send_json(handler, {"success": False, "error": "文件已存在"}, 400)
            return
        
        # 保存文件
        file_path.write_text(content, encoding='utf-8')
        
        # SSE 通知
        notify_knowledge_created(filename, {"size": len(content)})
        
        _send_json(handler, {
            "success": True,
            "data": {
                "filename": filename,
                "size": len(content)
            },
            "message": "文件创建成功"
        })
    except Exception as e:
        print(f"[ERROR] 创建知识库文件失败: {e}", flush=True)
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_update_knowledge_file(handler, filename):
    """更新知识库文件"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        data = json.loads(body)
        
        content = data.get('content', '')
        
        # 确保是 .md 文件
        if not filename.endswith('.md'):
            filename += '.md'
        
        # 安全检查
        if ".." in filename or "/" in filename or "\\" in filename:
            _send_json(handler, {"success": False, "error": "非法文件名"}, 400)
            return
        
        file_path = Path(KNOWLEDGE_BASE_DIR) / filename
        
        if not file_path.exists():
            _send_json(handler, {"success": False, "error": "文件不存在"}, 404)
            return
        
        # 保存文件
        file_path.write_text(content, encoding='utf-8')
        
        # SSE 通知
        notify_knowledge_updated(filename, {"size": len(content)})
        
        _send_json(handler, {
            "success": True,
            "data": {
                "filename": filename,
                "size": len(content)
            },
            "message": "文件更新成功"
        })
    except Exception as e:
        print(f"[ERROR] 更新知识库文件失败: {e}", flush=True)
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_delete_knowledge_file(handler, filename):
    """删除知识库文件"""
    try:
        # 确保是 .md 文件
        if not filename.endswith('.md'):
            filename += '.md'
        
        # 安全检查
        if ".." in filename or "/" in filename or "\\" in filename:
            _send_json(handler, {"success": False, "error": "非法文件名"}, 400)
            return
        
        file_path = Path(KNOWLEDGE_BASE_DIR) / filename
        
        if not file_path.exists():
            _send_json(handler, {"success": False, "error": "文件不存在"}, 404)
            return
        
        # 移动到回收站
        trash_dir = Path(KNOWLEDGE_BASE_DIR) / ".trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_name = f"{file_path.stem}.deleted.{timestamp}{file_path.suffix}"
        trash_path = trash_dir / trash_name
        
        shutil.move(str(file_path), str(trash_path))
        
        # SSE 通知
        notify_knowledge_deleted(filename, {"trash_path": str(trash_path)})
        
        _send_json(handler, {
            "success": True,
            "data": {
                "filename": filename,
                "trash_path": str(trash_path)
            },
            "message": "文件已删除"
        })
    except Exception as e:
        print(f"[ERROR] 删除知识库文件失败: {e}", flush=True)
        _send_json(handler, {"success": False, "error": str(e)}, 500)
