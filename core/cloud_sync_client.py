#!/usr/bin/env python3
"""
本地服务器云端同步客户端
功能：
1. 主动连接云端同步服务器（SSE长连接）
2. 接收云端推送的变更通知
3. 向云端上报本地变更
4. 断线重连和增量同步
5. 自动下载云端变更的文件
"""
import os
import json
import time
import threading
import requests
import shutil
from datetime import datetime
from typing import Callable, Dict, Optional
from urllib.parse import urljoin


def log(msg, tag="CloudSyncClient"):
    """统一日志输出，带时间戳"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{tag}] {msg}", flush=True)


class FileSyncManager:
    """文件同步管理器 - 处理云端到本地的文件同步"""
    
    def __init__(self, cloud_sync_url: str, cloud_file_url: str, local_base_dir: str = "."):
        """
        Args:
            cloud_sync_url: 云端同步服务器地址 (端口5033)
            cloud_file_url: 云端文件服务器地址 (端口5032)
            local_base_dir: 本地基础目录
        """
        self.cloud_sync_url = cloud_sync_url
        self.cloud_file_url = cloud_file_url
        self.local_base_dir = local_base_dir
    
    def sync_file(self, file_path: str, change_type: str) -> bool:
        """同步单个文件
        
        Args:
            file_path: 云端文件相对路径
            change_type: 变更类型 (created, modified, deleted)
        
        Returns:
            bool: 是否同步成功
        """
        local_path = os.path.join(self.local_base_dir, file_path)
        
        if change_type == 'deleted':
            # 删除本地文件
            return self._delete_local_file(local_path)
        else:
            # 下载云端文件
            return self._download_file(file_path, local_path)
    
    def _download_file(self, cloud_path: str, local_path: str) -> bool:
        """从云端下载文件"""
        try:
            # 构建云端文件URL（使用文件服务器地址 5032）
            file_url = urljoin(self.cloud_file_url + "/", cloud_path.lstrip('/'))
            
            log(f"[文件同步] 正在下载: {cloud_path}")
            
            # 创建本地目录
            local_dir = os.path.dirname(local_path)
            os.makedirs(local_dir, exist_ok=True)
            
            # 下载文件
            response = requests.get(file_url, timeout=30, stream=True)
            
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                log(f"[文件同步] 下载成功: {local_path}")
                return True
            else:
                log(f"[文件同步] 下载失败: {file_url} (状态码: {response.status_code})")
                return False
                
        except Exception as e:
            log(f"[文件同步] 下载异常: {e}")
            return False
    
    def _delete_local_file(self, local_path: str) -> bool:
        """删除本地文件"""
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                log(f"[文件同步] 已删除: {local_path}")
                return True
            else:
                log(f"[文件同步] 文件不存在，无需删除: {local_path}")
                return True
        except Exception as e:
            log(f"[文件同步] 删除失败: {e}")
            return False


class CloudSyncClient:
    """云端同步客户端 - 运行在本地服务器"""
    
    def __init__(self, cloud_sync_url: str, cloud_file_url: str = None, 
                 server_id: str = None, reconnect_interval: int = 5, 
                 max_reconnect_attempts: int = 10,
                 enable_file_sync: bool = True, local_base_dir: str = "."):
        """
        Args:
            cloud_sync_url: 云端同步服务器地址 (端口5033)
            cloud_file_url: 云端文件服务器地址 (端口5032)，默认从 sync_url 推导
        """
        self.cloud_sync_url = cloud_sync_url.rstrip('/')
        # 默认文件服务器地址：将 5033 替换为 5032
        if cloud_file_url:
            self.cloud_file_url = cloud_file_url.rstrip('/')
        else:
            self.cloud_file_url = self.cloud_sync_url.replace(':5033', ':5032')
        
        self.server_id = server_id or self._generate_server_id()
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        
        self._running = False
        self._connected = False
        self._reconnect_attempts = 0
        self._last_sync_timestamp = 0
        self._last_heartbeat = 0
        self._sse_thread: Optional[threading.Thread] = None
        self._event_handlers: Dict[str, Callable] = {}
        
        # 文件同步管理器
        self._file_sync_enabled = enable_file_sync
        self._file_sync: Optional[FileSyncManager] = None
        if enable_file_sync:
            self._file_sync = FileSyncManager(self.cloud_sync_url, self.cloud_file_url, local_base_dir)
        
        log(f"云端同步客户端初始化完成，服务器ID: {self.server_id}")
    
    def _generate_server_id(self) -> str:
        """生成服务器ID"""
        import uuid
        return f"local_{uuid.uuid4().hex[:8]}"
    
    def start(self):
        """启动同步客户端"""
        if self._running:
            return
        
        self._running = True
        self._reconnect_attempts = 0
        
        # 启动 SSE 连接线程
        self._sse_thread = threading.Thread(target=self._sse_loop, daemon=True)
        self._sse_thread.start()
        
        log("云端同步客户端已启动")
    
    def stop(self):
        """停止同步客户端"""
        self._running = False
        self._connected = False
        log("云端同步客户端已停止")
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器
        
        Args:
            event_type: 事件类型 (connected, file_change, catch_up_sync, heartbeat)
            handler: 处理函数
        """
        self._event_handlers[event_type] = handler
        log(f"注册事件处理器: {event_type}")
    
    def notify_change(self, change_type: str, file_path: str, **kwargs) -> bool:
        """向云端上报本地变更
        
        Args:
            change_type: 变更类型 (created, modified, deleted)
            file_path: 文件路径
            **kwargs: 额外信息
        
        Returns:
            bool: 是否上报成功
        """
        try:
            url = f"{self.cloud_sync_url}/api/cloud/notify"
            payload = {
                "server_id": self.server_id,
                "change_type": change_type,
                "file_path": file_path,
                **kwargs
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                log(f"变更已上报云端: {change_type} - {file_path}")
                return True
            else:
                log(f"上报变更失败: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            log(f"上报变更异常: {e}", "ERROR")
            return False
    
    def _sse_loop(self):
        """SSE 连接主循环（带断线重连）"""
        log("SSE连接线程已启动")
        
        last_check = time.time()
        
        while self._running:
            try:
                if not self._connected:
                    self._connect_sse()
                
                # 每30秒检查一次连接状态
                if time.time() - last_check > 30:
                    if not self._check_connection():
                        log("连接检查失败，重新连接...")
                        self._connected = False
                    last_check = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                log(f"SSE循环异常: {e}", "ERROR")
                self._connected = False
                time.sleep(self.reconnect_interval)
    
    def _check_connection(self) -> bool:
        """检查连接是否仍然活跃"""
        try:
            # 尝试获取云端统计信息
            url = f"{self.cloud_sync_url}/api/cloud/stats"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def _connect_sse(self):
        """建立 SSE 连接"""
        try:
            # 构建连接URL
            url = f"{self.cloud_sync_url}/api/cloud/sync"
            params = {
                "server_id": self.server_id,
                "last_sync": self._last_sync_timestamp
            }
            
            log(f"正在连接云端: {url}")
            
            # 使用 requests 建立 SSE 连接
            # 使用长超时，避免长时间没有数据时断开
            response = requests.get(url, params=params, stream=True, timeout=(10, None))
            
            if response.status_code != 200:
                log(f"连接云端失败: {response.status_code}", "ERROR")
                self._handle_reconnect()
                return
            
            log("云端连接已建立")
            self._connected = True
            self._reconnect_attempts = 0
            
            # 处理 SSE 事件流
            self._process_sse_stream(response)
            
        except requests.exceptions.RequestException as e:
            log(f"连接云端异常: {e}", "ERROR")
            self._handle_reconnect()
        except Exception as e:
            log(f"SSE连接异常: {e}", "ERROR")
            self._handle_reconnect()
    
    def _process_sse_stream(self, response):
        """处理 SSE 事件流"""
        buffer = ""
        
        try:
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if not self._running:
                    break
                
                if not chunk:
                    continue
                
                buffer += chunk
                
                # 处理完整的事件（以\n\n分隔）
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    self._handle_sse_event(event_text)
                    
        except Exception as e:
            log(f"处理SSE流异常: {e}", "ERROR")
            self._connected = False
    
    def _handle_sse_event(self, event_text: str):
        """处理单个 SSE 事件"""
        lines = event_text.strip().split("\n")
        event_type = "message"
        data = ""
        
        for line in lines:
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        
        if not data:
            return
        
        try:
            event_data = json.loads(data)
        except:
            event_data = {"raw": data}
        
        # 更新最后同步时间
        self._last_sync_timestamp = time.time()
        
        # 获取实际数据（云端包装了一层 data 字段）
        actual_data = event_data.get('data', event_data)
        
        # 调用对应的事件处理器
        handler = self._event_handlers.get(event_type)
        if handler:
            try:
                handler(actual_data)
            except Exception as e:
                log(f"事件处理器异常: {e}", "ERROR")
        
        # 内置事件处理
        if event_type == "connected":
            log(f"云端连接确认，服务器ID: {actual_data.get('server_id')}")
        
        elif event_type == "file_change":
            change_type = actual_data.get('change_type')
            file_path = actual_data.get('file_path')
            
            # 检查数据有效性
            if not file_path or not change_type:
                log(f"收到文件变更通知，但数据无效: {event_data}")
                return
            
            log(f"收到文件变更通知: {change_type} - {file_path}")
            
            # 自动同步文件
            if self._file_sync_enabled and self._file_sync:
                self._sync_file_async(file_path, change_type)
        
        elif event_type == "catch_up_sync":
            total = actual_data.get('total', 0)
            changes = actual_data.get('changes', [])
            log(f"收到追赶同步: {total} 条变更")
            
            # 批量同步文件
            if self._file_sync_enabled and self._file_sync:
                for change in changes:
                    self._sync_file_async(
                        change.get('file_path'),
                        change.get('change_type')
                    )
        
        elif event_type == "heartbeat":
            # 心跳事件，更新最后活跃时间
            self._last_heartbeat = time.time()
            # 可选：打印心跳日志（调试用，可以注释掉）
            # log(f"[心跳] 收到云端心跳")
    
    def _sync_file_async(self, file_path: str, change_type: str):
        """异步同步文件"""
        # 检查参数
        if not file_path or not change_type:
            log(f"[文件同步] 跳过: 无效参数 (file_path={file_path}, change_type={change_type})")
            return
        
        def sync_task():
            if self._file_sync:
                try:
                    success = self._file_sync.sync_file(file_path, change_type)
                    if success:
                        log(f"[文件同步] 完成: {change_type} - {file_path}")
                    else:
                        log(f"[文件同步] 失败: {change_type} - {file_path}")
                except Exception as e:
                    log(f"[文件同步] 异常: {e}")
        
        # 在后台线程执行同步
        threading.Thread(target=sync_task, daemon=True).start()
    
    def _handle_reconnect(self):
        """处理重连逻辑"""
        self._connected = False
        
        if self._reconnect_attempts >= self.max_reconnect_attempts:
            log("达到最大重连次数，停止重连", "ERROR")
            self._running = False
            return
        
        self._reconnect_attempts += 1
        delay = min(self.reconnect_interval * (2 ** (self._reconnect_attempts - 1)), 60)
        
        log(f"{delay}秒后尝试第{self._reconnect_attempts}次重连...")
        time.sleep(delay)
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "server_id": self.server_id,
            "connected": self._connected,
            "reconnect_attempts": self._reconnect_attempts,
            "last_sync": self._last_sync_timestamp,
            "cloud_sync_url": self.cloud_sync_url,
            "cloud_file_url": self.cloud_file_url
        }


# ═══════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════
_default_client: Optional[CloudSyncClient] = None


def init_cloud_sync(cloud_base_url: str, server_id: str = None) -> CloudSyncClient:
    """初始化云端同步客户端
    
    Args:
        cloud_base_url: 云端服务器地址，如 "http://120.26.84.224:5033"
        server_id: 本地服务器ID（可选，自动生成）
    
    Returns:
        CloudSyncClient: 同步客户端实例
    """
    global _default_client
    _default_client = CloudSyncClient(cloud_base_url, server_id)
    _default_client.start()
    return _default_client


def get_cloud_sync_client() -> Optional[CloudSyncClient]:
    """获取默认的云端同步客户端"""
    return _default_client


def notify_cloud_change(change_type: str, file_path: str, **kwargs) -> bool:
    """向云端上报变更（便捷函数）
    
    Args:
        change_type: 变更类型
        file_path: 文件路径
        **kwargs: 额外信息
    
    Returns:
        bool: 是否上报成功
    """
    if _default_client:
        return _default_client.notify_change(change_type, file_path, **kwargs)
    return False


# ═══════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    # 测试代码
    log("测试云端同步客户端...")
    
    # 创建客户端（连接到本地测试服务器）
    client = CloudSyncClient("http://localhost:5033", "test_local_server")
    
    # 注册事件处理器
    def on_file_change(data):
        log(f"处理文件变更: {data}")
    
    def on_catch_up(data):
        log(f"处理追赶同步: {data.get('total')} 条变更")
    
    client.register_event_handler("file_change", on_file_change)
    client.register_event_handler("catch_up_sync", on_catch_up)
    
    # 启动客户端
    client.start()
    
    try:
        # 运行一段时间
        time.sleep(30)
        
        # 测试上报变更
        client.notify_change("created", "assets/images/T423/test.jpg", 
                           file_hash="abc123", file_size=1024)
        
        time.sleep(10)
        
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
        log("测试完成")
