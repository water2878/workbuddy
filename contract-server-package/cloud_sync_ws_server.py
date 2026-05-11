#!/usr/bin/env python3
"""
云端同步服务器 - WebSocket版本
功能：
1. 管理多个本地服务器的WebSocket连接
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
import asyncio
import websockets
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

# 导入文件监控器
try:
    from file_monitor import FileMonitor
    FILE_MONITOR_ENABLED = True
except ImportError:
    FILE_MONITOR_ENABLED = False
    FileMonitor = None


def log(msg, tag="CloudSyncWS"):
    """统一日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{tag}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════
# 变更日志（云端存储所有变更历史）
# ═════════════════════════════════