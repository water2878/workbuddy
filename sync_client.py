#!/usr/bin/env python3
"""
SSE 同步客户端 - 实时监听云端变更并同步到本地
云端数据变化时，自动下载或删除本地对应文件
"""
import os
import sys
import json
import time
import requests
import shutil
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
from config import PRODUCT_IMAGES_DIR, KNOWLEDGE_BASE_DIR, CLOUD_IMAGES_SERVER, CLOUD_TOKEN


class SyncClient:
    """同步客户端"""
    
    def __init__(self):
        self.cloud_base = CLOUD_IMAGES_SERVER.rstrip('/') if CLOUD_IMAGES_SERVER else ''
        self.headers = {'Authorization': f'Bearer {CLOUD_TOKEN}'} if CLOUD_TOKEN else {}
        self.running = False
        self.stats = {
            'downloaded': 0,
            'deleted': 0,
            'errors': 0
        }
    
    def log(self, message: str):
        """打印日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {message}")
    
    def download_image(self, model: str, filename: str) -> bool:
        """从云端下载图片"""
        try:
            local_dir = Path(PRODUCT_IMAGES_DIR) / model
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / filename
            
            # 如果已存在，跳过
            if local_path.exists():
                return True
            
            # 下载图片
            url = f"{self.cloud_base}/assets/images/{model}/{filename}"
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                self.stats['downloaded'] += 1
                self.log(f"✅ 下载: {model}/{filename}")
                return True
            else:
                self.log(f"❌ 下载失败: {model}/{filename} - HTTP {response.status_code}")
                self.stats['errors'] += 1
                return False
                
        except Exception as e:
            self.log(f"❌ 下载异常: {model}/{filename} - {e}")
            self.stats['errors'] += 1
            return False
    
    def delete_image(self, model: str, filename: str) -> bool:
        """删除本地图片"""
        try:
            local_path = Path(PRODUCT_IMAGES_DIR) / model / filename
            if local_path.exists():
                local_path.unlink()
                self.stats['deleted'] += 1
                self.log(f"🗑️ 删除图片: {model}/{filename}")
            return True
        except Exception as e:
            self.log(f"❌ 删除图片失败: {model}/{filename} - {e}")
            self.stats['errors'] += 1
            return False
    
    def delete_product(self, model: str) -> bool:
        """删除本地产品目录"""
        try:
            local_dir = Path(PRODUCT_IMAGES_DIR) / model
            if local_dir.exists():
                shutil.rmtree(local_dir)
                self.stats['deleted'] += 1
                self.log(f"🗑️ 删除产品: {model}")
            return True
        except Exception as e:
            self.log(f"❌ 删除产品失败: {model} - {e}")
            self.stats['errors'] += 1
            return False
    
    def sync_product_images(self, model: str):
        """同步整个产品的图片"""
        try:
            self.log(f"📦 同步产品: {model}")
            
            # 获取云端图片列表
            url = f"{self.cloud_base}/api/materials/products/{model}/images"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                self.log(f"❌ 获取图片列表失败: {model}")
                return
            
            result = response.json()
            if not result.get('success'):
                self.log(f"❌ 获取图片列表失败: {model}")
                return
            
            cloud_images = result.get('data', {}).get('images', [])
            
            # 下载所有云端图片
            for img in cloud_images:
                filename = img['filename']
                self.download_image(model, filename)
            
            # 清理本地多余的图片
            local_dir = Path(PRODUCT_IMAGES_DIR) / model
            if local_dir.exists():
                cloud_filenames = {img['filename'] for img in cloud_images}
                for local_file in local_dir.iterdir():
                    if local_file.is_file() and local_file.name not in cloud_filenames:
                        local_file.unlink()
                        self.stats['deleted'] += 1
                        self.log(f"🗑️ 清理多余文件: {model}/{local_file.name}")
            
        except Exception as e:
            self.log(f"❌ 同步产品失败: {model} - {e}")
    
    def create_product(self, model: str) -> bool:
        """创建本地产品目录"""
        try:
            local_dir = Path(PRODUCT_IMAGES_DIR) / model
            local_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"📁 创建产品: {model}")
            return True
        except Exception as e:
            self.log(f"❌ 创建产品失败: {model} - {e}")
            self.stats['errors'] += 1
            return False

    def handle_event(self, event: dict):
        """处理 SSE 事件"""
        event_type = event.get('type')
        data = event.get('data', {})
        model = data.get('model')
        
        if not model:
            return
        
        if event_type == 'product_created':
            # 新产品，创建目录并同步所有图片
            self.create_product(model)
            self.sync_product_images(model)
        
        elif event_type == 'product_deleted':
            # 删除产品
            self.delete_product(model)
        
        elif event_type == 'image_uploaded':
            # 上传图片，下载该图片
            filename = data.get('filename')
            if filename:
                self.download_image(model, filename)
        
        elif event_type == 'image_deleted':
            # 删除图片
            filename = data.get('filename')
            if filename:
                self.delete_image(model, filename)
        
        elif event_type == 'knowledge_created':
            # 创建知识库文件
            filename = data.get('filename')
            if filename:
                self.download_knowledge(filename)
        
        elif event_type == 'knowledge_updated':
            # 更新知识库文件
            filename = data.get('filename')
            if filename:
                self.download_knowledge(filename)
        
        elif event_type == 'knowledge_deleted':
            # 删除知识库文件
            filename = data.get('filename')
            if filename:
                self.delete_knowledge(filename)
    
    def download_knowledge(self, filename: str) -> bool:
        """从云端下载知识库文件"""
        try:
            local_dir = Path(KNOWLEDGE_BASE_DIR)
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / filename
            
            # 下载文件
            url = f"{self.cloud_base}/api/materials/knowledge/{filename}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    content = result.get('data', {}).get('content', '')
                    local_path.write_text(content, encoding='utf-8')
                    self.stats['downloaded'] += 1
                    self.log(f"📄 下载知识库: {filename}")
                    return True
            
            self.log(f"❌ 下载知识库失败: {filename}")
            self.stats['errors'] += 1
            return False
            
        except Exception as e:
            self.log(f"❌ 下载知识库异常: {filename} - {e}")
            self.stats['errors'] += 1
            return False
    
    def delete_knowledge(self, filename: str) -> bool:
        """删除本地知识库文件"""
        try:
            local_path = Path(KNOWLEDGE_BASE_DIR) / filename
            if local_path.exists():
                local_path.unlink()
                self.stats['deleted'] += 1
                self.log(f"🗑️ 删除知识库: {filename}")
            return True
        except Exception as e:
            self.log(f"❌ 删除知识库失败: {filename} - {e}")
            self.stats['errors'] += 1
            return False
    
    def connect_sse(self):
        """连接 SSE 服务"""
        url = f"{self.cloud_base}/api/sse/events"
        
        try:
            self.log(f"🔗 连接 SSE: {url}")
            
            response = requests.get(
                url,
                headers={**self.headers, 'Accept': 'text/event-stream'},
                stream=True,
                timeout=30
            )
            
            if response.status_code != 200:
                self.log(f"❌ SSE 连接失败: HTTP {response.status_code}")
                return False
            
            self.log("✅ SSE 连接成功，开始监听...")
            
            # 读取 SSE 流
            for line in response.iter_lines():
                if not self.running:
                    break
                
                if line:
                    line = line.decode('utf-8')
                    
                    # 解析 SSE 消息
                    if line.startswith('event:'):
                        event_type = line[6:].strip()
                    elif line.startswith('data:'):
                        data_str = line[5:].strip()
                        try:
                            data = json.loads(data_str)
                            event = {
                                'type': data.get('type'),
                                'data': data.get('data', {})
                            }
                            self.handle_event(event)
                        except json.JSONDecodeError:
                            pass
                    elif line.startswith(':'):
                        # 心跳，忽略
                        pass
            
            return True
            
        except requests.exceptions.ReadTimeout:
            self.log("⏱️ SSE 连接超时，重新连接...")
            return False
        except Exception as e:
            self.log(f"❌ SSE 连接异常: {e}")
            return False
    
    def run(self):
        """运行同步客户端"""
        self.log("="*50)
        self.log("实时同步客户端启动")
        self.log(f"云端服务器: {self.cloud_base}")
        self.log("="*50)
        
        self.running = True
        
        try:
            while self.running:
                connected = self.connect_sse()
                
                if not connected:
                    # 连接失败，等待后重连
                    self.log("🔄 5秒后重新连接...")
                    time.sleep(5)
                else:
                    # 连接断开，立即重连
                    self.log("🔄 连接断开，重新连接...")
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            self.log("\n👋 收到停止信号")
        finally:
            self.running = False
            self.print_stats()
    
    def stop(self):
        """停止同步客户端"""
        self.running = False
    
    def print_stats(self):
        """打印统计信息"""
        self.log("="*50)
        self.log("同步统计:")
        self.log(f"  下载: {self.stats['downloaded']} 个文件")
        self.log(f"  删除: {self.stats['deleted']} 个文件")
        self.log(f"  错误: {self.stats['errors']} 个")
        self.log("="*50)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='实时同步客户端')
    parser.add_argument('--once', action='store_true', help='执行一次全量同步后退出')
    
    args = parser.parse_args()
    
    client = SyncClient()
    
    if args.once:
        # 全量同步
        client.log("执行全量同步...")
        try:
            # 同步产品图片
            url = f"{client.cloud_base}/api/materials/products"
            response = requests.get(url, headers=client.headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    products = result.get('data', {}).get('products', [])
                    for prod in products:
                        model = prod.get('model') if isinstance(prod, dict) else prod
                        if model:
                            client.sync_product_images(model)
            
            # 同步知识库
            client.log("同步知识库...")
            url = f"{client.cloud_base}/api/materials/knowledge"
            response = requests.get(url, headers=client.headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    files = result.get('data', {}).get('files', [])
                    for f in files:
                        filename = f.get('filename')
                        if filename:
                            client.download_knowledge(filename)
                            
        except Exception as e:
            client.log(f"全量同步失败: {e}")
        
        client.print_stats()
    else:
        # 实时同步
        client.run()


if __name__ == '__main__':
    main()
