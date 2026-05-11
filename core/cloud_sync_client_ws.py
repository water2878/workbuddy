#!/usr/bin/env python3
"""
本地服务器云端同步客户端 - WebSocket版本
与 cloud_sync_client.py 功能相同，但使用 WebSocket 替代 SSE
"""
import os
import json
import time
import asyncio
import threading
import shutil
import httpx
import websockets
from datetime import datetime
from typing import Callable, Dict, Optional


# ═══════════════════════════════════════════════════════
# 日志工具 - 统一使用 core.config.log
# ═══════════════════════════════════════════════════════
try:
    from core.config import log
except ImportError:
    # 兜底日志函数
    def log(msg, tag="CloudSyncClientWS"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{tag}] {msg}", flush=True)


class CloudSyncWebSocketClient:
    """云端同步 WebSocket 客户端 - 运行在本地服务器"""
    
    def __init__(self, cloud_ws_url: str, cloud_file_url: str = None,
                 server_id: str = None, reconnect_interval: int = 5,
                 max_reconnect_attempts: int = 10,
                 local_sync_dir: str = None):
        """
        Args:
            cloud_ws_url: 云端 WebSocket 服务器地址 (端口5033)
            cloud_file_url: 云端文件服务器地址 (端口5032)
            local_sync_dir: 本地同步目录，默认与云端保持一致
        """
        self.cloud_ws_url = cloud_ws_url
        self.cloud_file_url = cloud_file_url or cloud_ws_url.replace(':5033', ':5032').replace('ws://', 'http://')
        self.server_id = server_id or self._generate_server_id()
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        
        # 本地同步目录 - 默认是项目根目录（与云端监控的 assets/images 和 assets/products 对应）
        if local_sync_dir:
            self.local_sync_dir = local_sync_dir
        else:
            # 获取项目根目录（core 的上级目录）
            core_dir = os.path.dirname(os.path.abspath(__file__))
            self.local_sync_dir = os.path.dirname(core_dir)
        
        self._running = False
        self._connected = False
        self._reconnect_attempts = 0
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._event_handlers: Dict[str, Callable] = {}
        
        # 加载上次同步时间戳
        self._last_sync_timestamp = self._load_last_sync_timestamp()
    
    def _get_sync_state_file(self) -> str:
        """获取同步状态文件路径"""
        # 保存在本地同步目录下的 .sync 文件夹中
        sync_dir = os.path.join(self.local_sync_dir, '.sync')
        os.makedirs(sync_dir, exist_ok=True)
        return os.path.join(sync_dir, 'sync_state.json')
    
    def _load_last_sync_timestamp(self) -> float:
        """加载上次同步时间戳"""
        try:
            state_file = self._get_sync_state_file()
            if os.path.exists(state_file):
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    timestamp = state.get('last_sync_timestamp', 0)
                    log(f"加载上次同步时间戳: {timestamp}")
                    return timestamp
        except Exception as e:
            log(f"加载同步状态失败: {e}", "ERROR")
        return 0
    
    def _save_last_sync_timestamp(self, timestamp: float):
        """保存上次同步时间戳"""
        try:
            state_file = self._get_sync_state_file()
            state = {
                'last_sync_timestamp': timestamp,
                'server_id': self.server_id,
                'updated_at': datetime.now().isoformat()
            }
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            log(f"保存同步时间戳: {timestamp}")
        except Exception as e:
            log(f"保存同步状态失败: {e}", "ERROR")
    
    def _generate_server_id(self) -> str:
        """生成服务器ID"""
        import uuid
        return f"local_{uuid.uuid4().hex[:8]}"
    
    def start(self):
        """启动客户端（在线程中运行）"""
        if self._running:
            return
        
        self._running = True
        
        # 在后台线程运行 asyncio 事件循环
        def run_loop():
            asyncio.run(self._main_loop())
        
        threading.Thread(target=run_loop, daemon=True).start()
        log("WebSocket客户端已启动")
    
    def stop(self):
        """停止客户端"""
        self._running = False
        if self._websocket:
            asyncio.create_task(self._websocket.close())
        log("WebSocket客户端已停止")
    
    async def _main_loop(self):
        """主循环"""
        while self._running:
            try:
                if not self._connected:
                    await self._connect()
                
                # 保持连接
                await asyncio.sleep(1)
                
            except Exception as e:
                log(f"主循环异常: {e}", "ERROR")
                self._connected = False
                await asyncio.sleep(self.reconnect_interval)
    
    async def _connect(self):
        """建立 WebSocket 连接"""
        try:
            log(f"正在连接云端: {self.cloud_ws_url}")
            
            # 建立 WebSocket 连接（增加超时时间）
            self._websocket = await websockets.connect(
                self.cloud_ws_url,
                open_timeout=30,  # 连接超时30秒
                ping_interval=20,  # 每20秒发送ping
                ping_timeout=10    # ping超时10秒
            )
            
            # 发送注册信息
            register_msg = {
                "type": "register",
                "server_id": self.server_id,
                "last_sync": self._last_sync_timestamp
            }
            await self._websocket.send(json.dumps(register_msg))
            
            # 等待连接确认
            response = await self._websocket.recv()
            data = json.loads(response)
            
            if data.get("type") == "connected":
                log(f"云端连接确认，服务器ID: {data.get('data', {}).get('server_id')}")
                self._connected = True
                self._reconnect_attempts = 0
                
                # 启动消息处理循环
                asyncio.create_task(self._receive_loop())
            else:
                log(f"连接确认失败: {data}", "ERROR")
                await self._websocket.close()
                
        except Exception as e:
            log(f"连接云端异常: {e}", "ERROR")
            await self._handle_reconnect()
    
    async def _receive_loop(self):
        """接收消息循环"""
        try:
            log("开始接收消息循环...")
            async for message in self._websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    # 只记录非心跳消息，心跳消息静默处理
                    if msg_type not in ('heartbeat', 'pong'):
                        log(f"收到消息: {msg_type}")
                    
                    await self._handle_message(data)
                except Exception as e:
                    log(f"处理消息异常: {e}", "ERROR")
        except websockets.exceptions.ConnectionClosed:
            log("WebSocket连接关闭")
            self._connected = False
        except Exception as e:
            log(f"接收消息异常: {e}", "ERROR")
            self._connected = False
    
    async def _handle_message(self, data: dict):
        """处理收到的消息"""
        msg_type = data.get("type")
        msg_data = data.get("data", {})
        
        # 调用对应的事件处理器
        handler = self._event_handlers.get(msg_type)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(msg_data)
                else:
                    handler(msg_data)
            except Exception as e:
                log(f"事件处理器异常: {e}", "ERROR")
        
        # 内置事件处理
        if msg_type == "connected":
            log(f"云端连接确认，服务器ID: {msg_data.get('server_id')}")
        
        elif msg_type == "file_change":
            change_type = msg_data.get('change_type')
            file_path = msg_data.get('file_path')
            source_server = msg_data.get('source_server', 'unknown')
            log(f"收到文件变更通知: {change_type} - {file_path} (来自: {source_server})")
            
            # 执行文件同步操作，保持与云端一致
            await self._sync_file_from_cloud(change_type, file_path, msg_data)
        
        elif msg_type == "catch_up_sync":
            total = msg_data.get('total', 0)
            changes = msg_data.get('changes', [])
            log(f"收到追赶同步: {total} 条变更")
            
            # 逐条处理断线期间的变更
            for change in changes:
                change_type = change.get('change_type')
                file_path = change.get('file_path')
                source_server = change.get('source_server', 'unknown')
                log(f"处理追赶同步变更: {change_type} - {file_path} (来自: {source_server})")
                
                # 执行文件同步
                await self._sync_file_from_cloud(change_type, file_path, change)
            
            log(f"追赶同步完成，共处理 {len(changes)} 条变更")
            
            # 保存同步时间戳
            self._last_sync_timestamp = time.time()
            self._save_last_sync_timestamp(self._last_sync_timestamp)
        
        elif msg_type == "request_local_state":
            # 服务器请求上报本地文件状态（首次连接时的差异同步）
            log(f"收到本地状态上报请求")
            await self._report_local_state()
        
        elif msg_type == "diff_sync":
            # 收到差异同步（首次连接时使用）
            total = msg_data.get('total', 0)
            changes = msg_data.get('changes', [])
            message = msg_data.get('message', '')
            log(f"收到差异同步: {message}, 共 {total} 个文件")
            
            # 逐条处理差异同步的变更
            for change in changes:
                change_type = change.get('change_type')
                file_path = change.get('file_path')
                log(f"处理差异同步变更: {change_type} - {file_path}")
                
                # 执行文件同步
                await self._sync_file_from_cloud(change_type, file_path, change)
            
            log(f"差异同步完成，共处理 {len(changes)} 个文件")
            
            # 更新最后同步时间戳
            self._last_sync_timestamp = time.time()
        
        elif msg_type == "heartbeat":
            # 响应心跳（静默处理，不打印日志）
            await self._send_ping()
        
        elif msg_type == "pong":
            # 收到心跳响应（静默处理）
            pass
    
    async def _send_ping(self):
        """发送心跳"""
        if self._websocket and self._connected:
            try:
                await self._websocket.send(json.dumps({"type": "ping"}))
            except:
                self._connected = False
    
    async def _report_local_state(self):
        """上报本地文件状态给服务器（用于首次连接的差异同步）"""
        try:
            log(f"正在扫描本地文件状态...")
            local_files = []
            
            # 只扫描与云端监控对应的目录：assets/images 和 assets/products
            watch_dirs = [
                os.path.join(self.local_sync_dir, 'assets', 'images'),
                os.path.join(self.local_sync_dir, 'assets', 'products')
            ]
            
            for watch_dir in watch_dirs:
                if not os.path.exists(watch_dir):
                    log(f"目录不存在，跳过: {watch_dir}")
                    continue
                    
                log(f"扫描目录: {watch_dir}")
                for root, dirs, files in os.walk(watch_dir):
                    # 排除缓存文件夹
                    dirs[:] = [d for d in dirs if d not in ('.trash', '__pycache__', '.git', '.svn')]
                    
                    # 扫描文件夹
                    for dirname in dirs:
                        dir_path = os.path.join(root, dirname)
                        try:
                            stat = os.stat(dir_path)
                            # 转换为相对路径
                            rel_path = os.path.relpath(dir_path, self.local_sync_dir)
                            rel_path = rel_path.replace('\\', '/')
                            local_files.append({
                                'path': rel_path,
                                'hash': '',  # 文件夹不需要hash
                                'size': 0,
                                'mtime': stat.st_mtime,
                                'is_dir': True
                            })
                        except:
                            pass
                    
                    # 扫描文件
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        try:
                            stat = os.stat(file_path)
                            # 计算文件hash
                            file_hash = self._get_file_hash(file_path)
                            # 转换为相对路径
                            rel_path = os.path.relpath(file_path, self.local_sync_dir)
                            rel_path = rel_path.replace('\\', '/')
                            local_files.append({
                                'path': rel_path,
                                'hash': file_hash,
                                'size': stat.st_size,
                                'mtime': stat.st_mtime,
                                'is_dir': False
                            })
                        except:
                            pass
            
            log(f"本地文件扫描完成: {len(local_files)} 个文件/文件夹")
            
            # 发送给服务器
            if self._websocket and self._connected:
                await self._websocket.send(json.dumps({
                    'type': 'local_state_report',
                    'data': {
                        'files': local_files,
                        'total': len(local_files)
                    }
                }))
                log(f"已上报本地文件状态给服务器")
            else:
                log(f"WebSocket未连接，无法上报本地状态", "ERROR")
                
        except Exception as e:
            log(f"上报本地状态异常: {e}", "ERROR")
            import traceback
            log(f"异常详情: {traceback.format_exc()}", "ERROR")
    
    def _get_file_hash(self, file_path: str) -> str:
        """计算文件hash"""
        try:
            import hashlib
            hash_obj = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except:
            return ''
    
    async def _sync_file_from_cloud(self, change_type: str, file_path: str, msg_data: dict):
        """
        从云端同步文件到本地，保持与云端一致
        
        Args:
            change_type: 变更类型 (created/modified/deleted)
            file_path: 文件路径（相对路径）
            msg_data: 消息数据
        """
        try:
            # 构建本地文件完整路径
            local_file_path = os.path.join(self.local_sync_dir, file_path)
            
            # 检查是否是文件夹（通过消息数据或本地判断）
            is_dir = msg_data.get('is_dir', False)
            
            if change_type == 'deleted':
                # 删除本地文件或文件夹
                if os.path.exists(local_file_path):
                    try:
                        if os.path.isdir(local_file_path):
                            shutil.rmtree(local_file_path)
                            log(f"已删除本地文件夹: {local_file_path}")
                        else:
                            os.remove(local_file_path)
                            log(f"已删除本地文件: {local_file_path}")
                    except Exception as e:
                        log(f"删除本地失败: {local_file_path}, 错误: {e}", "ERROR")
                else:
                    # 检查父文件夹是否也不存在（说明父文件夹已被删除）
                    parent_dir = os.path.dirname(local_file_path)
                    if not os.path.exists(parent_dir):
                        # 父文件夹已被删除，这是正常的，不打印日志
                        pass
                    else:
                        # 父文件夹存在但文件不存在，可能是已经被删除了
                        log(f"本地不存在，无需删除: {file_path}")
            
            elif change_type in ('created', 'modified'):
                if is_dir:
                    # 创建文件夹
                    if not os.path.exists(local_file_path):
                        os.makedirs(local_file_path, exist_ok=True)
                        log(f"已创建本地文件夹: {local_file_path}")
                    else:
                        log(f"本地文件夹已存在: {local_file_path}")
                else:
                    # 下载文件从云端
                    await self._download_file_from_cloud(file_path, local_file_path)
            
            else:
                log(f"未知的变更类型: {change_type}", "WARN")
                
        except Exception as e:
            log(f"同步文件异常: {e}", "ERROR")
            import traceback
            log(f"异常详情: {traceback.format_exc()}", "ERROR")
    
    async def _download_file_from_cloud(self, cloud_file_path: str, local_file_path: str):
        """
        从云端下载文件到本地
        
        Args:
            cloud_file_path: 云端文件路径（相对路径）
            local_file_path: 本地文件路径
        """
        try:
            # 确保本地目录存在
            local_dir = os.path.dirname(local_file_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
                log(f"创建本地目录: {local_dir}")
            
            # 构建云端文件下载URL
            # 假设云端文件可以通过 HTTP 访问，路径为 /api/files/{file_path}
            download_url = f"{self.cloud_file_url}/api/files/{cloud_file_path.replace('\\', '/')}"
            
            log(f"开始下载文件: {download_url} -> {local_file_path}")
            
            # 使用 httpx 下载文件
            async with httpx.AsyncClient() as client:
                response = await client.get(download_url, timeout=60.0)
                
                if response.status_code == 200:
                    # 保存文件
                    with open(local_file_path, 'wb') as f:
                        f.write(response.content)
                    
                    log(f"文件下载成功: {local_file_path} ({len(response.content)} 字节)")
                else:
                    log(f"下载文件失败: HTTP {response.status_code} - {download_url}", "ERROR")
                    
        except Exception as e:
            log(f"下载文件异常: {e}", "ERROR")
            import traceback
            log(f"异常详情: {traceback.format_exc()}", "ERROR")
    
    async def notify_change(self, change_type: str, file_path: str, **kwargs) -> bool:
        """向云端上报变更"""
        if not self._connected or not self._websocket:
            log("未连接到云端，无法上报变更")
            return False
        
        try:
            message = {
                "type": "notify_change",
                "data": {
                    "change_type": change_type,
                    "file_path": file_path,
                    **kwargs
                }
            }
            await self._websocket.send(json.dumps(message))
            log(f"变更已上报云端: {change_type} - {file_path}")
            return True
        except Exception as e:
            log(f"上报变更异常: {e}", "ERROR")
            return False
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        self._event_handlers[event_type] = handler
        log(f"注册事件处理器: {event_type}")
    
    async def _handle_reconnect(self):
        """处理重连逻辑"""
        self._connected = False
        
        if self._reconnect_attempts >= self.max_reconnect_attempts:
            log("达到最大重连次数，停止重连", "ERROR")
            self._running = False
            return
        
        self._reconnect_attempts += 1
        delay = min(self.reconnect_interval * (2 ** (self._reconnect_attempts - 1)), 60)
        
        log(f"{delay}秒后尝试第{self._reconnect_attempts}次重连...")
        await asyncio.sleep(delay)
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected


# 便捷函数
def init_cloud_sync_ws(cloud_ws_url: str, server_id: str = None) -> CloudSyncWebSocketClient:
    """初始化 WebSocket 云端同步客户端"""
    client = CloudSyncWebSocketClient(cloud_ws_url, server_id=server_id)
    client.start()
    return client


if __name__ == "__main__":
    # 测试
    client = CloudSyncWebSocketClient("ws://localhost:5033")
    
    def on_file_change(data):
        print(f"文件变更: {data}")
    
    client.register_event_handler("file_change", on_file_change)
    client.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.stop()
