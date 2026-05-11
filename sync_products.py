#!/usr/bin/env python3
"""
产品数据同步工具 - 从云端同步到本地
用法:
    python sync_products.py              # 同步所有产品
    python sync_products.py T523         # 只同步指定型号
"""
import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# 添加 core 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))

from config import (
    PRODUCT_IMAGES_DIR,
    CLOUD_IMAGES_SERVER, CLOUD_TOKEN
)


class ProductSync:
    """产品数据同步器 - 云端 -> 本地"""
    
    def __init__(self):
        self.cloud_base = CLOUD_IMAGES_SERVER.rstrip('/') if CLOUD_IMAGES_SERVER else ''
        self.headers = {'Authorization': f'Bearer {CLOUD_TOKEN}'} if CLOUD_TOKEN else {}
        self.downloaded = 0
        self.skipped = 0
        self.errors = 0
    
    def check_cloud(self) -> bool:
        """检查云端是否可用"""
        if not self.cloud_base:
            print("错误: 云端服务器未配置")
            return False
        try:
            response = requests.get(f"{self.cloud_base}/api/materials/products", 
                                   headers=self.headers, timeout=5)
            if response.status_code == 200:
                return True
            print(f"错误: 云端服务器返回 HTTP {response.status_code}")
            return False
        except Exception as e:
            print(f"错误: 无法连接云端服务器 - {e}")
            return False
    
    def get_cloud_products(self) -> List[Dict]:
        """