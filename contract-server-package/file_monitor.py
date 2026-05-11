#!/usr/bin/env python3
"""
文件监控器 - 监控云端文件夹变化
当文件增删改时，通知云端同步服务器广播给所有本地服务器
"""
import os
import time
import threading
import hashlib
from datetime import datetime
from typing import Dict, Callable, Optional


def log(msg, tag="FileMonitor"):
    """统一日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{tag}] {msg}", flush=True)


class FileMonitor:
    """文件监控器"""
    
    def __init__(self, watch_paths: list, interval: int = 5):
        """
        Args:
            watch_paths: 监控的文件夹列表
            interval: 检查间隔（秒）
        """
        self.watch_paths = watch_paths
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._file_states: Dict[str, dict] = {}
        self._callbacks: list = []
        self._no_change_count = 0  # 无变化计数
        self._check_count = 0  # 检查次数
    
    def add_callback(self, callback: Callable):
        """添加变更回调函数
        
        Args:
            callback: 回调函数，参数为 (change_type, file_path, file_hash)
        """
        self._callbacks.append(callback)
    
    def start(self):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        
        # 初始扫描
        self._scan_all()
        
        # 启动监控线程
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
        log(f"文件监控已启动，监控路径: {self.watch_paths}")
    
    def stop(self):
        """停止监控"""
        self._running = False
        log("文件监控已停止")
    
    def _get_file_hash(self, file_path: str) -> str:
        """计算文件哈希"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return ""
    
    def _scan_directory(self, path: str) -> Dict[str, dict]:
        """扫描目录获取文件和文件夹状态"""
        files = {}
        try:
            for root, dirs, filenames in os.walk(path):
                # 排除缓存文件夹
                dirs[:] = [d for d in dirs if d not in ('.trash', '__pycache__', '.git', '.svn')]
                
                # 扫描文件夹
                for dirname in dirs:
                    dir_path = os.path.join(root, dirname)
                    try:
                        stat = os.stat(dir_path)
                        files[dir_path] = {
                            'mtime': stat.st_mtime,
                            'size': 0,
                            'hash': '',
                            'is_dir': True
                        }
                    except:
                        pass
                
                # 扫描文件
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    try:
                        stat = os.stat(file_path)
                        files[file_path] = {
                            'mtime': stat.st_mtime,
                            'size': stat.st_size,
                            'hash': self._get_file_hash(file_path),
                            'is_dir': False
                        }
                    except:
                        pass
        except Exception as e:
            log(f"扫描目录失败 {path}: {e}", "ERROR")
        return files
    
    def _scan_all(self):
        """扫描所有监控路径"""
        new_states = {}
        for path in self.watch_paths:
            if os.path.exists(path):
                new_states.update(self._scan_directory(path))
        self._file_states = new_states
        log(f"初始扫描完成，共 {len(self._file_states)} 个文件")
    
    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                time.sleep(self.interval)
                self._check_changes()
            except Exception as e:
                log(f"监控异常: {e}", "ERROR")
    
    def _check_changes(self):
        """检查文件变化"""
        current_states = {}
        for path in self.watch_paths:
            if os.path.exists(path):
                scanned = self._scan_directory(path)
                current_states.update(scanned)
        
        has_changes = False
        
        # 检查新增和修改
        for file_path, state in current_states.items():
            if file_path not in self._file_states:
                # 新增文件
                log(f"发现新增文件: {file_path}")
                self._notify_change('created', file_path, state['hash'], state['size'])
                has_changes = True
            else:
                old_state = self._file_states[file_path]
                if state['hash'] != old_state['hash'] or state['mtime'] != old_state['mtime']:
                    # 修改文件
                    log(f"发现修改文件: {file_path}")
                    self._notify_change('modified', file_path, state['hash'], state['size'])
                    has_changes = True
        
        # 检查删除
        for file_path in self._file_states:
            if file_path not in current_states:
                log(f"发现删除文件: {file_path}")
                self._notify_change('deleted', file_path, "", 0)
                has_changes = True
        
        # 更新状态
        self._file_states = current_states
        self._check_count += 1
        
        # 只在有变化时打印日志
        if has_changes:
            log(f"文件检查完成，发现变化，当前共 {len(self._file_states)} 个文件")
            self._no_change_count = 0
        else:
            self._no_change_count += 1
            # 每小时打印一次（假设 interval=5秒，则 720次=1小时）
            if self._no_change_count >= 720:
                log(f"文件检查完成，无变化，当前共 {len(self._file_states)} 个文件（已稳定运行1小时）")
                self._no_change_count = 0
    
    def _notify_change(self, change_type: str, file_path: str, file_hash: str, file_size: int):
        """通知变更"""
        log(f"检测到变更: {change_type} - {file_path}")
        log(f"回调数量: {len(self._callbacks)}")
        for i, callback in enumerate(self._callbacks):
            try:
                log(f"执行回调 {i+1}/{len(self._callbacks)}...")
                callback(change_type, file_path, file_hash, file_size)
                log(f"回调 {i+1} 执行完成")
            except Exception as e:
                log(f"回调 {i+1} 异常: {e}", "ERROR")
                import traceback
                log(f"异常详情: {traceback.format_exc()}", "ERROR")


if __name__ == '__main__':
    # 测试
    def on_change(change_type, file_path, file_hash, file_size):
        print(f"变更: {change_type} - {file_path}")
    
    monitor = FileMonitor(['./test_watch'])
    monitor.add_callback(on_change)
    monitor.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
