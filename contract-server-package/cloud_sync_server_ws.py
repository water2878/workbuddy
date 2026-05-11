#!/usr/bin/env python3
"""
云端同步服务器 - WebSocket版本
与 cloud_sync_server.py 功能相同，但使用 WebSocket 替代 SSE
"""
import os
import sys
import json
import time
import asyncio
import threading
import websockets
from datetime import datetime
from typing import Dict, Set, Optional
from dataclasses import dataclass, field

# 导入共享的变更日志
from cloud_sync_server import CloudChangeLog, log

# 导入文件监控器
try:
    from file_monitor import FileMonitor
    FILE_MONITOR_ENABLED = True
except ImportError:
    FILE_MONITOR_ENABLED = False
    FileMonitor = None


@dataclass
class WSClient:
    """WebSocket客户端连接"""
    server_id: str
    websocket: websockets.WebSocketServerProtocol
    connected_at: float = field(default_factory=time.time)
    last_ping: float = field(default_factory=time.time)
    
    async def send(self, event_type: str, data: dict):
        """发送消息到客户端"""
        try:
            message = {
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            message_str = json.dumps(message, ensure_ascii=False)
            log(f"[WSClient:{self.server_id}] 发送消息: {message_str[:100]}...")
            await self.websocket.send(message_str)
            log(f"[WSClient:{self.server_id}] 消息发送成功")
            return True
        except Exception as e:
            log(f"[WSClient:{self.server_id}] 发送消息失败: {e}", "ERROR")
            return False
    
    def is_timeout(self, timeout_seconds: int = 60) -> bool:
        """检查是否超时"""
        return time.time() - self.last_ping > timeout_seconds


class CloudSyncWebSocketServer:
    """云端同步 WebSocket 服务器"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5034):
        self.host = host
        self.port = port
        self.clients: Dict[str, WSClient] = {}
        self.clients_lock = asyncio.Lock()
        self.change_log = CloudChangeLog()
        self._running = False
        self._file_monitor: Optional[FileMonitor] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def start(self):
        """启动 WebSocket 服务器"""
        self._running = True
        self._loop = asyncio.get_running_loop()
        
        # 启动心跳检查任务
        asyncio.create_task(self._heartbeat_loop())
        
        # 启动文件监控
        if FILE_MONITOR_ENABLED and FileMonitor:
            self._start_file_monitor()
        
        log(f"WebSocket服务器启动 ws://{self.host}:{self.port}")
        
        async with websockets.serve(self._handle_client, self.host, self.port, ping_interval=None):
            await asyncio.Future()  # 永久运行
    
    def _start_file_monitor(self):
        """启动文件监控"""
        # 只监控云端 assets 文件夹（不监控合同）
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
            """文件变更回调 - 广播给所有客户端"""
            try:
                log(f"[文件监控] 检测到文件变更: {change_type} - {file_path}")
                
                # 转换为相对路径（用于本地同步）
                base_dir = os.path.dirname(__file__)
                try:
                    rel_path = os.path.relpath(file_path, base_dir)
                    # 统一使用正斜杠
                    rel_path = rel_path.replace('\\', '/')
                except Exception as e:
                    log(f"[文件监控] 路径转换失败: {e}", "ERROR")
                    rel_path = file_path.replace('\\', '/')
                
                log(f"[文件监控] 处理变更: {change_type} - {rel_path}")
                
                # 判断是否是文件夹
                is_dir = os.path.isdir(file_path)
                
                # 使用 asyncio.run_coroutine_threadsafe 在事件循环中执行异步操作
                if self._loop and self._loop.is_running():
                    log(f"[文件监控] 提交异步任务到事件循环")
                    
                    def handle_future_result(future):
                        try:
                            future.result()
                            log(f"[文件监控] 异步任务执行成功")
                        except Exception as e:
                            log(f"[文件监控] 异步任务执行失败: {e}", "ERROR")
                    
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_cloud_file_change(change_type, rel_path, file_hash, file_size, is_dir),
                        self._loop
                    )
                    future.add_done_callback(handle_future_result)
                    log(f"[文件监控] 异步任务已提交")
                else:
                    log(f"[文件监控] 警告: 事件循环未运行，无法提交任务", "WARN")
            except Exception as e:
                log(f"[文件监控] 回调处理异常: {e}", "ERROR")
                import traceback
                log(f"[文件监控] 异常详情: {traceback.format_exc()}", "ERROR")
        
        self._file_monitor.add_callback(on_file_change)
        self._file_monitor.start()
        log(f"文件监控已启动，监控路径: {watch_paths}")
    
    async def _handle_cloud_file_change(self, change_type: str, file_path: str, file_hash: str, file_size: int, is_dir: bool = False):
        """处理云端文件变更"""
        try:
            log(f"[文件监控] 开始处理云端文件变更: {change_type} - {file_path} (is_dir={is_dir})")
            
            # 记录到变更日志
            self.change_log.log_change(
                server_id="cloud_server",
                change_type=change_type,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size
            )
            log(f"[文件监控] 变更已记录到日志")
            
            # 广播给所有客户端
            log(f"[文件监控] 开始广播给客户端...")
            await self.broadcast('file_change', {
                'source_server': 'cloud_server',
                'change_type': change_type,
                'file_path': file_path,
                'file_hash': file_hash,
                'file_size': file_size,
                'is_dir': is_dir
            }, exclude_server='cloud_server')
            
            log(f"[文件监控] 云端文件变更已广播: {change_type} - {file_path}")
        except Exception as e:
            log(f"[文件监控] 处理云端文件变更异常: {e}", "ERROR")
            import traceback
            log(f"[文件监控] 异常详情: {traceback.format_exc()}", "ERROR")
    
    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol):
        """处理客户端连接"""
        server_id = None
        
        try:
            # 等待客户端发送注册信息
            message = await websocket.recv()
            data = json.loads(message)
            
            if data.get("type") != "register":
                await websocket.send(json.dumps({"error": "Expected register message"}))
                return
            
            server_id = data.get("server_id", f"ws_{id(websocket)}")
            last_sync = data.get("last_sync", 0)
            
            # 创建客户端对象
            client = WSClient(server_id=server_id, websocket=websocket)
            
            async with self.clients_lock:
                # 如果已存在，先移除旧连接
                if server_id in self.clients:
                    old_client = self.clients[server_id]
                    try:
                        await old_client.websocket.close()
                    except:
                        pass
                    log(f"客户端 {server_id} 重新连接")
                
                self.clients[server_id] = client
                log(f"客户端 {server_id} 已连接，当前连接数: {len(self.clients)}")
            
            # 发送连接确认
            await client.send("connected", {"server_id": server_id})
            
            # 同步策略
            if last_sync > 0:
                # 断线重连：发送追赶同步（断线期间的变更）
                await self._send_catch_up_sync(client, last_sync)
            else:
                # 第一次连接：请求客户端上报本地文件状态，进行差异同步
                log(f"客户端 {server_id} 首次连接，准备差异同步")
                await client.send("request_local_state", {"message": "请上报本地文件状态"})
            
            # 处理客户端消息
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(client, data)
                except Exception as e:
                    log(f"处理消息异常: {e}", "ERROR")
            
        except websockets.exceptions.ConnectionClosed:
            log(f"客户端 {server_id} 连接关闭")
        except Exception as e:
            log(f"客户端处理异常: {e}", "ERROR")
        finally:
            if server_id:
                async with self.clients_lock:
                    if server_id in self.clients:
                        del self.clients[server_id]
                        log(f"客户端 {server_id} 已断开，当前连接数: {len(self.clients)}")
    
    async def _handle_message(self, client: WSClient, data: dict):
        """处理客户端消息"""
        msg_type = data.get("type")
        
        if msg_type == "ping":
            # 心跳响应
            client.last_ping = time.time()
            await client.send("pong", {"time": time.time()})
        
        elif msg_type == "notify_change":
            # 客户端上报变更
            change_data = data.get("data", {})
            await self._handle_client_change(
                client.server_id,
                change_data.get("change_type"),
                change_data.get("file_path"),
                change_data
            )
        
        elif msg_type == "local_state_report":
            # 客户端上报本地文件状态（用于首次连接的差异同步）
            local_files = data.get("data", {}).get("files", [])
            log(f"收到客户端 {client.server_id} 的本地文件状态: {len(local_files)} 个文件")
            await self._send_diff_sync(client, local_files)
    
    async def _handle_client_change(self, server_id: str, change_type: str, file_path: str, extra: dict):
        """处理客户端变更通知"""
        log(f"收到变更 [{server_id}]: {change_type} - {file_path}")
        
        # 记录到变更日志
        self.change_log.log_change(
            server_id=server_id,
            change_type=change_type,
            file_path=file_path,
            file_hash=extra.get('file_hash'),
            file_size=extra.get('file_size'),
            extra=extra
        )
        
        # 广播给其他客户端
        await self.broadcast('file_change', {
            'source_server': server_id,
            'change_type': change_type,
            'file_path': file_path,
            **extra
        }, exclude_server=server_id)
        
        log(f"变更已广播: {change_type} - {file_path}")
    
    async def _send_catch_up_sync(self, client: WSClient, since_timestamp: float):
        """发送追赶同步"""
        missed = self.change_log.get_changes_since(since_timestamp, exclude_server=client.server_id)
        
        if missed:
            log(f"客户端 {client.server_id} 有 {len(missed)} 条 missed 变更")
            await client.send('catch_up_sync', {
                'changes': missed,
                'total': len(missed),
                'from_timestamp': since_timestamp
            })
    
    async def _send_diff_sync(self, client: WSClient, local_files: list):
        """发送差异同步（首次连接时使用）
        
        对比本地文件和云端文件，只同步差异部分
        """
        try:
            log(f"开始计算差异同步...")
            
            # 获取云端当前文件状态
            cloud_files = {}
            for watch_path in self._file_monitor.watch_paths if self._file_monitor else []:
                if os.path.exists(watch_path):
                    files = self._file_monitor._scan_directory(watch_path) if self._file_monitor else {}
                    cloud_files.update(files)
            
            # 构建本地文件字典（路径 -> {hash, is_dir}）
            local_file_dict = {}
            for f in local_files:
                file_path = f.get('path', '')
                file_hash = f.get('hash', '')
                is_dir = f.get('is_dir', False)
                if file_path:
                    # 使用 (hash, is_dir) 元组来区分文件夹和文件
                    local_file_dict[file_path] = {'hash': file_hash, 'is_dir': is_dir}
            
            # 计算差异
            diff_changes = []
            
            # 获取服务器所在目录（contract-server-package）
            server_dir = os.path.dirname(os.path.abspath(__file__))
            server_dir_name = os.path.basename(server_dir)
            
            # 1. 云端有但本地没有，或云端更新的文件
            for cloud_path, cloud_state in cloud_files.items():
                # 转换为相对路径（去掉 contract-server-package 前缀）
                try:
                    rel_path = os.path.relpath(cloud_path, server_dir)
                    rel_path = rel_path.replace('\\', '/')
                    # 去掉开头的 contract-server-package/
                    if rel_path.startswith(server_dir_name + '/'):
                        rel_path = rel_path[len(server_dir_name) + 1:]
                except:
                    rel_path = cloud_path.replace('\\', '/')
                    # 去掉开头的 contract-server-package/
                    if rel_path.startswith(server_dir_name + '/'):
                        rel_path = rel_path[len(server_dir_name) + 1:]
                
                local_info = local_file_dict.get(rel_path)
                cloud_hash = cloud_state.get('hash', '')
                cloud_is_dir = cloud_state.get('is_dir', False)
                
                if local_info is None:
                    # 云端有，本地没有 -> 需要创建
                    diff_changes.append({
                        'change_type': 'created',
                        'file_path': rel_path,
                        'file_hash': cloud_hash,
                        'file_size': cloud_state.get('size', 0),
                        'is_dir': cloud_is_dir
                    })
                elif local_info['hash'] != cloud_hash:
                    # 云端和本地不一致 -> 需要更新（仅针对文件，文件夹不需要更新）
                    if not cloud_is_dir:
                        diff_changes.append({
                            'change_type': 'modified',
                            'file_path': rel_path,
                            'file_hash': cloud_hash,
                            'file_size': cloud_state.get('size', 0),
                            'is_dir': cloud_is_dir
                        })
            
            # 2. 本地有但云端没有的文件（可选：删除本地或保留）
            # 这里选择保留本地文件，不删除
            
            # 发送差异同步
            if diff_changes:
                log(f"差异同步: 需要同步 {len(diff_changes)} 个文件")
                await client.send('diff_sync', {
                    'changes': diff_changes,
                    'total': len(diff_changes),
                    'message': '首次连接差异同步'
                })
            else:
                log(f"差异同步: 本地和云端文件一致，无需同步")
                await client.send('diff_sync', {
                    'changes': [],
                    'total': 0,
                    'message': '文件已是最新'
                })
                
        except Exception as e:
            log(f"差异同步异常: {e}", "ERROR")
            import traceback
            log(f"异常详情: {traceback.format_exc()}", "ERROR")
    
    async def broadcast(self, event_type: str, data: dict, exclude_server: str = None):
        """广播消息给所有客户端"""
        try:
            async with self.clients_lock:
                clients = list(self.clients.items())
            
            if not clients:
                log(f"[广播] 没有客户端连接，跳过广播")
                return
            
            log(f"[广播] 开始广播到 {len(clients)} 个客户端 (排除: {exclude_server})")
            dead_clients = []
            success_count = 0
            
            for server_id, client in clients:
                if server_id == exclude_server:
                    log(f"[广播] 跳过排除的客户端: {server_id}")
                    continue
                
                try:
                    if await client.send(event_type, data):
                        success_count += 1
                        log(f"[广播] 成功发送到客户端: {server_id}")
                    else:
                        log(f"[广播] 发送到客户端失败: {server_id}")
                        dead_clients.append(server_id)
                except Exception as e:
                    log(f"[广播] 发送到客户端 {server_id} 异常: {e}", "ERROR")
                    dead_clients.append(server_id)
            
            log(f"[广播] 广播完成: 成功 {success_count}/{len(clients)} 个客户端")
            
            # 清理断开的客户端
            if dead_clients:
                async with self.clients_lock:
                    for server_id in dead_clients:
                        if server_id in self.clients:
                            del self.clients[server_id]
                log(f"[广播] 清理了 {len(dead_clients)} 个断开客户端")
        except Exception as e:
            log(f"[广播] 广播异常: {e}", "ERROR")
            import traceback
            log(f"[广播] 异常详情: {traceback.format_exc()}", "ERROR")
    
    async def _heartbeat_loop(self):
        """心跳检查循环"""
        while self._running:
            try:
                await asyncio.sleep(30)
                
                async with self.clients_lock:
                    clients = list(self.clients.items())
                
                dead_clients = []
                
                for server_id, client in clients:
                    if client.is_timeout(60):
                        log(f"客户端 {server_id} 心跳超时")
                        dead_clients.append(server_id)
                        try:
                            await client.websocket.close()
                        except:
                            pass
                    else:
                        # 发送心跳
                        await client.send('heartbeat', {'time': time.time()})
                
                if dead_clients:
                    async with self.clients_lock:
                        for server_id in dead_clients:
                            if server_id in self.clients:
                                del self.clients[server_id]
                    log(f"清理了 {len(dead_clients)} 个超时客户端，当前连接数: {len(self.clients)}")
                    
            except Exception as e:
                log(f"心跳检查异常: {e}", "ERROR")


async def main():
    """启动 WebSocket 服务器"""
    server = CloudSyncWebSocketServer(port=5033)
    try:
        await server.start()
    finally:
        # 停止文件监控
        if server._file_monitor:
            server._file_monitor.stop()
            log("文件监控已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("服务器已停止")
