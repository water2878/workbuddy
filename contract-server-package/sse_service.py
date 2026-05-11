"""
SSE (Server-Sent Events) 服务 - 实时推送数据变更
云端数据变化时，主动推送到所有连接的客户端
"""
import json
import threading
import queue
import time
from datetime import datetime
from typing import Dict, List, Callable, Optional
import socket

# 客户端连接列表: client_id -> {'handler': handler, 'queue': Queue}
_clients: Dict[str, dict] = {}
_clients_lock = threading.Lock()

# 消息队列（用于广播）
_broadcast_queue = queue.Queue()

# 事件回调函数
_event_handlers: Dict[str, List[Callable]] = {}

# 广播线程
_broadcast_thread: Optional[threading.Thread] = None


def _start_broadcast_thread():
    """启动广播线程"""
    global _broadcast_thread
    if _broadcast_thread is None or not _broadcast_thread.is_alive():
        _broadcast_thread = threading.Thread(target=_broadcast_worker, daemon=True)
        _broadcast_thread.start()
        print("[SSE] 广播线程已启动")


def _broadcast_worker():
    """广播工作线程 - 从队列中获取事件并推送给所有客户端"""
    while True:
        try:
            event = _broadcast_queue.get(timeout=1.0)
            if event is None:
                continue

            # 获取所有客户端
            with _clients_lock:
                clients = list(_clients.items())

            # 推送给每个客户端
            dead_clients = []
            for client_id, client_info in clients:
                try:
                    handler = client_info['handler']
                    event_data = json.dumps(event)
                    message = f"id: {event['id']}\nevent: {event['type']}\ndata: {event_data}\n\n"
                    handler.wfile.write(message.encode())
                    handler.wfile.flush()
                    print(f"[SSE] 已推送到客户端 {client_id}: {event['type']}")
                except (socket.error, BrokenPipeError) as e:
                    print(f"[SSE] 客户端 {client_id} 连接已断开")
                    dead_clients.append(client_id)
                except Exception as e:
                    print(f"[SSE] 推送到客户端 {client_id} 失败: {e}")
                    dead_clients.append(client_id)

            # 清理断开的客户端
            with _clients_lock:
                for client_id in dead_clients:
                    if client_id in _clients:
                        del _clients[client_id]

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[SSE] 广播线程异常: {e}")


def register_event_handler(event_type: str, handler: Callable):
    """注册事件处理器

    Args:
        event_type: 事件类型 (product_created, product_deleted, image_uploaded, image_deleted)
        handler: 处理函数
    """
    if event_type not in _event_handlers:
        _event_handlers[event_type] = []
    _event_handlers[event_type].append(handler)


def unregister_event_handler(event_type: str, handler: Callable):
    """注销事件处理器"""
    if event_type in _event_handlers:
        if handler in _event_handlers[event_type]:
            _event_handlers[event_type].remove(handler)


def broadcast_event(event_type: str, data: dict):
    """广播事件到所有连接的客户端

    Args:
        event_type: 事件类型
        data: 事件数据
    """
    event = {
        "id": datetime.now().timestamp(),
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": data
    }

    # 添加到广播队列
    _broadcast_queue.put(event)

    # 调用事件处理器
    if event_type in _event_handlers:
        for handler in _event_handlers[event_type]:
            try:
                handler(data)
            except Exception as e:
                print(f"[SSE] 事件处理器异常: {e}")

    print(f"[SSE] 广播事件: {event_type}, 数据: {data}")


def handle_sse_request(handler, path: str):
    """处理 SSE 请求

    Args:
        handler: HTTP handler
        path: 请求路径

    Returns:
        bool: 是否处理了请求
    """
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(path)

    # SSE 订阅端点
    if parsed.path == "/api/sse/events":
        query = parse_qs(parsed.query)
        client_id = query.get("client_id", ["anonymous"])[0]

        # 确保广播线程已启动
        _start_broadcast_thread()

        # 设置 SSE 响应头
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()

        # 注册客户端
        with _clients_lock:
            _clients[client_id] = {'handler': handler}

        print(f"[SSE] 客户端连接: {client_id}, 当前连接数: {len(_clients)}")

        # 发送初始连接成功事件
        try:
            handler.wfile.write(f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n".encode())
            handler.wfile.flush()
        except Exception as e:
            print(f"[SSE] 发送连接事件失败: {e}")
            with _clients_lock:
                if client_id in _clients:
                    del _clients[client_id]
            return True

        # 保持连接，定期发送心跳
        try:
            while True:
                time.sleep(30)  # 每30秒发送一次心跳
                try:
                    handler.wfile.write(b":heartbeat\n\n")
                    handler.wfile.flush()
                except (socket.error, BrokenPipeError):
                    break
                except Exception as e:
                    print(f"[SSE] 发送心跳失败: {e}")
                    break
        except Exception as e:
            print(f"[SSE] 连接异常: {e}")
        finally:
            with _clients_lock:
                if client_id in _clients:
                    del _clients[client_id]
            print(f"[SSE] 客户端断开: {client_id}, 当前连接数: {len(_clients)}")

        return True

    return False


# 便捷函数：在数据变更时调用
def notify_product_created(model: str, details: dict = None):
    """通知产品创建"""
    broadcast_event("product_created", {"model": model, **(details or {})})


def notify_product_deleted(model: str, details: dict = None):
    """通知产品删除"""
    broadcast_event("product_deleted", {"model": model, **(details or {})})


def notify_image_uploaded(model: str, filename: str, details: dict = None):
    """通知图片上传"""
    data = {"model": model, "filename": filename}
    if details:
        data.update(details)
    broadcast_event("image_uploaded", data)


def notify_image_deleted(model: str, filename: str, details: dict = None):
    """通知图片删除"""
    data = {"model": model, "filename": filename}
    if details:
        data.update(details)
    broadcast_event("image_deleted", data)


def notify_knowledge_created(filename: str, details: dict = None):
    """通知知识库文件创建"""
    data = {"filename": filename}
    if details:
        data.update(details)
    broadcast_event("knowledge_created", data)


def notify_knowledge_updated(filename: str, details: dict = None):
    """通知知识库文件更新"""
    data = {"filename": filename}
    if details:
        data.update(details)
    broadcast_event("knowledge_updated", data)


def notify_knowledge_deleted(filename: str, details: dict = None):
    """通知知识库文件删除"""
    data = {"filename": filename}
    if details:
        data.update(details)
    broadcast_event("knowledge_deleted", data)
