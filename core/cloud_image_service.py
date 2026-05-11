"""
云端图片服务 - 实现产品图片的云端存储和同步
"""
import os
import requests
from pathlib import Path
from typing import Optional, Dict, List
from config import (
    CLOUD_IMAGES_ENABLED, CLOUD_IMAGES_SERVER, CLOUD_TOKEN,
    PRODUCT_IMAGES_DIR, log
)

# 云端图片缓存
_cloud_image_cache: Dict[str, List[str]] = {}


def is_cloud_enabled() -> bool:
    """检查云端图片功能是否启用"""
    return CLOUD_IMAGES_ENABLED and CLOUD_IMAGES_SERVER


def get_cloud_base_url() -> str:
    """获取云端图片基础 URL"""
    return CLOUD_IMAGES_SERVER.rstrip('/')


def upload_image_to_cloud(model: str, local_path: str, filename: str) -> Optional[str]:
    """上传图片到云端
    
    Args:
        model: 产品型号
        local_path: 本地图片路径
        filename: 文件名
        
    Returns:
        云端图片 URL，失败返回 None
    """
    if not is_cloud_enabled():
        return None
    
    try:
        url = f"{get_cloud_base_url()}/api/materials/products/{model}/images/upload"
        
        with open(local_path, 'rb') as f:
            files = {'image': (filename, f, 'image/jpeg')}
            data = {'model': model}
            headers = {'Authorization': f'Bearer {CLOUD_TOKEN}'} if CLOUD_TOKEN else {}
            
            response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    cloud_url = result.get('data', {}).get('url') or result.get('data', {}).get('path')
                    log(f"[云端] 图片上传成功: {filename} -> {cloud_url}")
                    return cloud_url
                else:
                    log(f"[云端] 上传失败: {result.get('error', '未知错误')}")
            else:
                log(f"[云端] 上传失败: HTTP {response.status_code}")
                
    except Exception as e:
        log(f"[云端] 上传异常: {e}")
    
    return None


def delete_image_from_cloud(model: str, filename: str) -> bool:
    """从云端删除图片
    
    Args:
        model: 产品型号
        filename: 文件名
        
    Returns:
        是否删除成功
    """
    if not is_cloud_enabled():
        return False
    
    try:
        url = f"{get_cloud_base_url()}/api/materials/products/{model}/images/{filename}"
        headers = {'Authorization': f'Bearer {CLOUD_TOKEN}'} if CLOUD_TOKEN else {}
        
        response = requests.delete(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            log(f"[云端] 图片删除成功: {filename}")
            return True
        else:
            log(f"[云端] 删除失败: HTTP {response.status_code}")
            
    except Exception as e:
        log(f"[云端] 删除异常: {e}")
    
    return False


def sync_images_from_cloud(model: str) -> List[str]:
    """从云端同步图片列表到本地
    
    Args:
        model: 产品型号
        
    Returns:
        本地图片路径列表
    """
    if not is_cloud_enabled():
        return []
    
    try:
        url = f"{get_cloud_base_url()}/api/materials/products/{model}/images"
        headers = {'Authorization': f'Bearer {CLOUD_TOKEN}'} if CLOUD_TOKEN else {}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                cloud_images = result.get('data', {}).get('images', [])
                local_paths = []
                
                # 下载云端图片到本地缓存
                for img in cloud_images:
                    cloud_url = img.get('url') or img.get('path')
                    filename = img.get('filename')
                    
                    if cloud_url and filename:
                        local_path = download_image_from_cloud(model, cloud_url, filename)
                        if local_path:
                            local_paths.append(local_path)
                
                log(f"[云端] 同步完成: {model} 共 {len(local_paths)} 张图片")
                return local_paths
                
    except Exception as e:
        log(f"[云端] 同步异常: {e}")
    
    return []


def download_image_from_cloud(model: str, cloud_url: str, filename: str) -> Optional[str]:
    """从云端下载图片到本地
    
    Args:
        model: 产品型号
        cloud_url: 云端图片 URL
        filename: 文件名
        
    Returns:
        本地图片路径，失败返回 None
    """
    try:
        # 本地缓存路径
        local_dir = Path(PRODUCT_IMAGES_DIR) / model
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / filename
        
        # 如果本地已存在，跳过下载
        if local_path.exists():
            return str(local_path)
        
        # 下载图片
        if cloud_url.startswith('http'):
            full_url = cloud_url
        else:
            full_url = f"{get_cloud_base_url()}{cloud_url}"
        
        response = requests.get(full_url, timeout=30)
        
        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(response.content)
            log(f"[云端] 下载成功: {filename}")
            return str(local_path)
        else:
            log(f"[云端] 下载失败: HTTP {response.status_code}")
            
    except Exception as e:
        log(f"[云端] 下载异常: {e}")
    
    return None


def get_cloud_image_url(model: str, filename: str) -> Optional[str]:
    """获取云端图片的访问 URL
    
    Args:
        model: 产品型号
        filename: 文件名
        
    Returns:
        云端图片 URL，未启用云端返回 None
    """
    if not is_cloud_enabled():
        return None
    
    return f"{get_cloud_base_url()}/api/materials/products/{model}/images/{filename}"


def list_cloud_images(model: str) -> List[Dict]:
    """获取云端图片列表
    
    Args:
        model: 产品型号
        
    Returns:
        图片信息列表
    """
    if not is_cloud_enabled():
        return []
    
    try:
        url = f"{get_cloud_base_url()}/api/materials/products/{model}/images"
        headers = {'Authorization': f'Bearer {CLOUD_TOKEN}'} if CLOUD_TOKEN else {}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return result.get('data', {}).get('images', [])
                
    except Exception as e:
        log(f"[云端] 获取列表异常: {e}")
    
    return []
