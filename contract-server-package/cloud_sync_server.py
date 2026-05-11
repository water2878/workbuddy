#!/usr/bin/env python3
"""
云端同步服务器 - 接收多个本地服务器的连接
功能：
1. 管理多个本地服务器的SSE长连接
2. 接收本地服务器的文件变更通知
3. 向所有连接的本地服务器广播变更
4. 支持增量同步（断线重连后追赶）
5. 监控云端文件夹变化，自动同步到所有本地服务器
"""
import os
import sys
import json
import time
import threading
import queue
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 导入文件监控器
try:
    from file_monitor import FileMonitor
    FILE_MONITOR_ENABLED = True
except ImportError:
    FILE_MONITOR_ENABLED = False
    FileMonitor = None

# ═══════════════════════════════════════════════════════
# 日志工具
# ═══════════════════════════════════════════════════════
def log(msg, tag="CloudSync"):
    """统一日志输出，带时间戳"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{tag}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════
# 变更日志（云端存储所有变更历史）
# ═══════════════════════════════════════════════════════
class CloudChangeLog:
    """云端变更日志 - 记录所有本地服务器的变更"""
    
    def __init__(self, db_path="data/cloud_changes.db"):
        import sqlite3
        
        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        self.db_path = db_path
        self.lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        import sqlite3
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    local_server_id TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_hash TEXT,
                    file_size INTEGER,
                    extra_data TEXT
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON changes(timestamp)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_server_time 
                ON changes(local_server_id, timestamp)
            ''')
            
            conn.commit()
        
        log(f"云端变更日志初始化完成: {self.db_path}")
    
    def log_change(self, server_id: str, change_type: str, file_path: str,
                   file_hash: str = None, file_size: int = 0, extra: dict = None):
        """记录变更"""
        import sqlite3
        
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        INSERT INTO changes 
                        (timestamp, local_server_id, change_type, file_path, file_hash, file_size, extra_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        time.time(),
                        server_id,
                        change_type,
                        file_path,
                        file_hash,
                        file_size,
                        json.dumps(extra) if extra else None
                    ))
                    conn.commit()
                    log(f"记录变更 [{server_id}]: {change_type} - {file_path}")
            except Exception as e:
                log(f"记录变更失败: {e}", "ERROR")
    
    def get_changes_since(self, since_timestamp: float, 
                          exclude_server: str = None,
                          limit: int = 1000) -> List[Dict]:
        """获取某个时间点之后的所有变更"""
        import sqlite3
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if exclude_server:
                cursor = conn.execute('''
                    SELECT * FROM changes 
                    WHERE timestamp > ? AND local_server_id != ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                ''', (since_timestamp, exclude_server, limit))
            else:
                cursor = conn.execute('''
                    SELECT * FROM changes 
                    WHERE timestamp > ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                ''', (since_timestamp, limit))
            
            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                if row_dict.get('extra_data'):
                    try:
                        row_dict['extra_data'] = json.loads(row_dict['extra_data'])
                    except:
                        pass
                results.append(row_dict)
            
            return results


# ═══════════════════════════════════════════════════════
# 本地服务器连接管理
# ═══════════════════════════════════════════════════════
@dataclass
class LocalServerConnection:
    """本地服务器连接信息"""
    server_id: str
    handler: object
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    last_sync_timestamp: float = 0
    is_alive: bool = True
    
    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = time.time()
    
    def is_timeout(self, timeout_seconds: int = 120) -> bool:
        """检查是否超时（2分钟）"""
        return time.time() - self.last_heartbeat > timeout_seconds
    
    def send_event(self, event_type: str, data: dict) -> bool:
        """发送事件到本地服务器"""
        try:
            event = {
                "id": time.time(),
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            event_data = json.dumps(event, ensure_ascii=False)
            message = f"id: {event['id']}\nevent: {event['type']}\ndata: {event_data}\n\n"
            self.handler.wfile.write(message.encode())
            self.handler.wfile.flush()
            return True
        except Exception as e:
            log(f"发送事件到本地服务器 {self.server_id} 失败: {e}", "ERROR")
            self.is_alive = False
            return False


class LocalServerManager:
    """本地服务器连接管理器"""
    
    def __init__(self, heartbeat_interval: int = 30, timeout_seconds: int = 120):
        self.servers: Dict[str, LocalServerConnection] = {}
        self.servers_lock = threading.RLock()
        self.heartbeat_interval = heartbeat_interval
        self.timeout_seconds = timeout_seconds
        self.change_log = CloudChangeLog()
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._file_monitor: Optional[FileMonitor] = None
    
    def start(self):
        """启动管理器"""
        self._running = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        
        # 启动文件监控（监控云端文件夹变化）
        if FILE_MONITOR_ENABLED and FileMonitor:
            self._start_file_monitor()
        
        log("本地服务器管理器已启动")
    
    def _start_file_monitor(self):
        """启动文件监控"""
        # 监控云端 assets 文件夹
        watch_paths = [
            os.path.join(os.path.dirname(__file__), "assets", "images"),
            os.path.join(os.path.dirname(__file__), "assets", "products")
        ]
        
        # 只监控存在的路径
        watch_paths = [p for p in watch_paths if os.path.exists(p)]
        
        if not watch_paths:
            log("没有可监控的文件夹，跳过文件监控")
            return
        
        self._file_monitor = FileMonitor(watch_paths, interval=5)
        
        # 添加变更回调
        def on_file_change(change_type, file_path, file_hash, file_size):
            """文件变更回调 - 广播给所有本地服务器"""
            log(f"[文件监控] 云端文件变更: {change_type} - {file_path}")
            
            # 转换为相对路径（用于本地同步）
            base_dir = os.path.dirname(__file__)
            try:
                rel_path = os.path.relpath(file_path, base_dir)
                # 统一使用正斜杠
                rel_path = rel_path.replace('\\', '/')
            except:
                rel_path = file_path.replace('\\', '/')
            
            # 记录变更并广播（模拟来自云端服务器的变更）
            self.handle_local_change(
                server_id="cloud_server",
                change_type=change_type,
                file_path=rel_path,
                file_hash=file_hash,
                file_size=file_size
            )
        
        self._file_monitor.add_callback(on_file_change)
        self._file_monitor.start()
        log(f"文件监控已启动，监控路径: {watch_paths}")
    
    def stop(self):
        """停止管理器"""
        self._running = False
        
        # 停止文件监控
        if self._file_monitor:
            self._file_monitor.stop()
        
        with self.servers_lock:
            for server in self.servers.values():
                server.is_alive = False
            self.servers.clear()
        log("本地服务器管理器已停止")
    
    def register_server(self, handler, server_id: str = None, 
                        last_sync: float = 0) -> LocalServerConnection:
        """注册本地服务器连接"""
        if not server_id:
            server_id = f"local_{uuid.uuid4().hex[:8]}"
        
        server = LocalServerConnection(
            server_id=server_id,
            handler=handler,
            last_sync_timestamp=last_sync
        )
        
        with self.servers_lock:
            # 如果已存在相同server_id，先移除旧连接
            if server_id in self.servers:
                old_server = self.servers[server_id]
                old_server.is_alive = False
                log(f"本地服务器 {server_id} 重新连接，断开旧连接")
            
            self.servers[server_id] = server
        
        log(f"本地服务器 {server_id} 已连接，当前连接数: {len(self.servers)}")
        
        # 如果有最后同步时间，触发增量同步
        if last_sync > 0:
            self._trigger_catch_up_sync(server)
        
        return server
    
    def unregister_server(self, server_id: str):
        """注销本地服务器连接"""
        with self.servers_lock:
            if server_id in self.servers:
                server = self.servers[server_id]
                server.is_alive = False
                del self.servers[server_id]
                log(f"本地服务器 {server_id} 已断开，当前连接数: {len(self.servers)}")
    
    def broadcast_to_all(self, event_type: str, data: dict, exclude_server: str = None):
        """广播事件到所有本地服务器"""
        with self.servers_lock:
            servers = list(self.servers.items())
        
        dead_servers = []
        
        for server_id, server in servers:
            if server_id == exclude_server:
                continue
            
            if not server.is_alive:
                dead_servers.append(server_id)
                continue
            
            if not server.send_event(event_type, data):
                dead_servers.append(server_id)
        
        # 清理断开的连接
        if dead_servers:
            with self.servers_lock:
                for server_id in dead_servers:
                    if server_id in self.servers:
                        del self.servers[server_id]
            log(f"清理了 {len(dead_servers)} 个断开的本地服务器")
    
    def handle_local_change(self, server_id: str, change_type: str, file_path: str, **kwargs):
        """处理本地服务器的变更通知"""
        # 打印变更日志
        log(f"收到变更 [{server_id}]: {change_type} - {file_path}")
        
        # 记录到云端变更日志
        self.change_log.log_change(
            server_id=server_id,
            change_type=change_type,
            file_path=file_path,
            file_hash=kwargs.get('file_hash'),
            file_size=kwargs.get('file_size'),
            extra=kwargs
        )
        
        # 广播给其他本地服务器
        self.broadcast_to_all('file_change', {
            'source_server': server_id,
            'change_type': change_type,
            'file_path': file_path,
            **kwargs
        }, exclude_server=server_id)
        
        log(f"变更已广播: {change_type} - {file_path}")
    
    def _trigger_catch_up_sync(self, server: LocalServerConnection):
        """触发追赶同步"""
        try:
            missed_changes = self.change_log.get_changes_since(
                server.last_sync_timestamp,
                exclude_server=server.server_id
            )
            
            if missed_changes:
                log(f"本地服务器 {server.server_id} 有 {len(missed_changes)} 条 missed 变更")
                
                server.send_event('catch_up_sync', {
                    'changes': missed_changes,
                    'total': len(missed_changes),
                    'from_timestamp': server.last_sync_timestamp,
                    'to_timestamp': time.time()
                })
            else:
                log(f"本地服务器 {server.server_id} 没有 missed 变更")
                
        except Exception as e:
            log(f"追赶同步失败: {e}", "ERROR")
    
    def _heartbeat_loop(self):
        """心跳检测循环"""
        log("心跳检测线程已启动")
        
        while self._running:
            try:
                time.sleep(self.heartbeat_interval)
                
                with self.servers_lock:
                    servers = list(self.servers.items())
                
                dead_servers = []
                
                for server_id, server in servers:
                    # 发送心跳
                    if server.is_alive:
                        if not server.send_event('heartbeat', {'time': time.time()}):
                            dead_servers.append(server_id)
                    
                    # 检查超时
                    if server.is_timeout(self.timeout_seconds):
                        log(f"本地服务器 {server_id} 心跳超时")
                        server.is_alive = False
                        dead_servers.append(server_id)
                
                # 清理超时连接
                if dead_servers:
                    with self.servers_lock:
                        for server_id in dead_servers:
                            if server_id in self.servers:
                                del self.servers[server_id]
                    log(f"清理了 {len(dead_servers)} 个超时本地服务器，当前连接数: {len(self.servers)}")
                    
            except Exception as e:
                log(f"心跳检测异常: {e}", "ERROR")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self.servers_lock:
            active_count = sum(1 for s in self.servers.values() if s.is_alive)
            return {
                'total_servers': len(self.servers),
                'active_servers': active_count,
                'is_running': self._running
            }


# ═══════════════════════════════════════════════════════
# HTTP 处理器
# ═══════════════════════════════════════════════════════
class CloudSyncHandler(BaseHTTPRequestHandler):
    
    def _send_json(self, data, status=200):
        """发送 JSON 响应"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # SSE 订阅端点 - 本地服务器连接到此接收推送
        if path == "/api/cloud/sync":
            self._handle_sync_connection(parsed)
            return
        
        # 获取统计信息
        if path == "/api/cloud/stats":
            stats = server_manager.get_stats()
            self._send_json({"success": True, "data": stats})
            return
        
        self._send_json({"success": False, "error": "Not found"}, 404)
    
    def do_POST(self):
        """处理 POST 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # 本地服务器上报变更
        if path == "/api/cloud/notify":
            self._handle_change_notification()
            return
        
        self._send_json({"success": False, "error": "Not found"}, 404)
    
    def _handle_sync_connection(self, parsed):
        """处理 SSE 同步连接"""
        query = parse_qs(parsed.query)
        server_id = query.get("server_id", [""])[0]
        last_sync = float(query.get("last_sync", ["0"])[0])
        
        if not server_id:
            self._send_json({"success": False, "error": "Missing server_id"}, 400)
            return
        
        # 设置 SSE 响应头
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        # 注册本地服务器
        server = server_manager.register_server(
            handler=self,
            server_id=server_id,
            last_sync=last_sync
        )
        
        log(f"本地服务器 {server_id} SSE连接已建立")
        
        try:
            # 发送连接成功事件
            self.wfile.write(f"event: connected\ndata: {json.dumps({'server_id': server_id})}\n\n".encode())
            self.wfile.flush()
            
            # 保持连接
            while server.is_alive:
                time.sleep(1)
                
        except Exception as e:
            log(f"SSE连接异常: {e}")
        finally:
            server_manager.unregister_server(server_id)
            log(f"本地服务器 {server_id} SSE连接已关闭")
    
    def _handle_change_notification(self):
        """处理变更通知"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'
            data = json.loads(body)
            
            server_id = data.get('server_id')
            change_type = data.get('change_type')
            file_path = data.get('file_path')
            
            if not all([server_id, change_type, file_path]):
                self._send_json({"success": False, "error": "Missing required fields"}, 400)
                return
            
            # 处理变更
            server_manager.handle_local_change(
                server_id=server_id,
                change_type=change_type,
                file_path=file_path,
                file_hash=data.get('file_hash'),
                file_size=data.get('file_size'),
                extra=data.get('extra')
            )
            
            self._send_json({"success": True, "message": "Change recorded and broadcasted"})
            
        except Exception as e:
            log(f"处理变更通知失败: {e}", "ERROR")
            self._send_json({"success": False, "error": str(e)}, 500)
    
    def log_message(self, format, *args):
        """禁用默认日志"""
        pass


# ═══════════════════════════════════════════════════════
# 全局管理器实例
# ═══════════════════════════════════════════════════════
server_manager = LocalServerManager()


# ═══════════════════════════════════════════════════════
# 启动函数
# ═══════════════════════════════════════════════════════
def main():
    import sys
    
    port = int(os.environ.get("CLOUD_SYNC_PORT", "5033"))
    
    log("═══════════════════════════════════════")
    log("云端同步服务器 v1.0")
    log(f"端口: {port}")
    log("═══════════════════════════════════════")
    
    # 启动管理器
    server_manager.start()
    
    # 启动 HTTP 服务器
    server = ThreadingHTTPServer(("0.0.0.0", port), CloudSyncHandler)
    log(f"服务器启动 http://0.0.0.0:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("服务器正在停止...")
        server_manager.stop()
        server.shutdown()
        log("服务器已停止")


if __name__ == "__main__":
    main()
