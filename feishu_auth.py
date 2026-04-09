#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书用户授权脚本 - 获取 user_access_token
"""
import urllib.request
import urllib.parse
import json
import time
import webbrowser

APP_ID = "cli_a93fb4f24f785bc3"

# 设备授权流程
def get_device_code():
    url = "https://accounts.feishu.cn/oauth/v2/device/code"
    data = urllib.parse.urlencode({
        "client_id": APP_ID,
        "scope": "im:chat im:message:readonly contact:user:readonly offline_access"
    }).encode()
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def poll_token(device_code, interval=5, expires_in=300):
    url = "https://accounts.feishu.cn/oauth/v2/device/token"
    deadline = time.time() + expires_in
    
    while time.time() < deadline:
        time.sleep(interval)
        
        data = urllib.parse.urlencode({
            "client_id": APP_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
        }).encode()
        
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if "access_token" in result:
                    return result
        except urllib.error.HTTPError as e:
            error = json.loads(e.read())
            if error.get("error") == "authorization_pending":
                print("等待授权...")
                continue
            elif error.get("error") == "slow_down":
                interval += 5
                continue
            else:
                raise RuntimeError(f"授权失败: {error}")
    
    raise RuntimeError("授权超时")

def main():
    print("开始飞书用户授权流程...")
    print("=" * 50)
    
    # 1. 获取设备码
    print("\n1. 正在请求设备码...")
    device_info = get_device_code()
    
    device_code = device_info["device_code"]
    user_code = device_info["user_code"]
    verification_uri = device_info["verification_uri"]
    
    print(f"\n2. 请在浏览器中打开以下链接并授权:")
    print(f"   {verification_uri}")
    print(f"\n   用户码: {user_code}")
    
    # 尝试自动打开浏览器
    try:
        webbrowser.open(verification_uri)
        print("   (已尝试自动打开浏览器)")
    except:
        pass
    
    print("\n3. 等待授权完成...")
    token_info = poll_token(device_code)
    
    print("\n" + "=" * 50)
    print("授权成功!")
    print(f"User Access Token: {token_info['access_token'][:30]}...")
    print(f"Refresh Token: {token_info.get('refresh_token', 'N/A')[:30]}...")
    
    # 保存到文件
    with open("feishu_user_token.json", "w") as f:
        json.dump(token_info, f, indent=2)
    print("\nToken 已保存到 feishu_user_token.json")

if __name__ == "__main__":
    main()
