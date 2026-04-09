#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 OAuth 授权获取 user_access_token，然后获取指定 chat_id 的聊天记录
"""

import urllib.request
import urllib.parse
import json
import webbrowser
import time
from datetime import datetime, timedelta

# 飞书应用配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"

BASE_URL = "https://open.feishu.cn/open-apis"
ACCOUNTS_URL = "https://accounts.feishu.cn"

# 指定的 chat_id
TARGET_CHAT_ID = "oc_d9e39d842488bad6ad9a45c6f31508d4"

def post_form(url, data):
    """发送 POST 表单请求"""
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except:
            return {"error": f"HTTP {e.code}"}

def post_json(url, data, headers=None):
    """发送 POST JSON 请求"""
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def get_user_token_by_device_flow():
    """使用设备授权流程获取 user_access_token"""
    print("=" * 70)
    print("飞书 OAuth 设备授权流程")
    print("=" * 70)
    
    # Step 1: 开始设备授权
    print("\n[步骤1] 请求设备授权码...")
    url = f"{ACCOUNTS_URL}/oauth/v2/device/code"
    data = {
        "app_id": APP_ID,
        "scope": "im:message:readonly im:chat:readonly contact:user.readonly"
    }
    result = post_form(url, data)
    
    if "error" in result:
        print(f"[错误] {result.get('error_description', result['error'])}")
        return None
    
    device_code = result.get("device_code")
    user_code = result.get("user_code")
    verification_url = result.get("verification_url")
    expires_in = int(result.get("expires_in", 1800))
    interval = int(result.get("interval", 5))
    
    print(f"[成功] 获取授权码")
    print(f"\n" + "=" * 70)
    print("请在浏览器中完成授权：")
    print(f"  访问: {verification_url}")
    print(f"  输入: {user_code}")
    print("=" * 70)
    
    # 自动打开浏览器
    try:
        webbrowser.open(verification_url)
        print("\n[提示] 已尝试自动打开浏览器")
    except:
        pass
    
    # Step 2: 轮询获取 token
    print(f"\n[步骤2] 等待授权完成...")
    print("(请在浏览器中点击确认授权)\n")
    
    token_url = f"{ACCOUNTS_URL}/oauth/v2/device/token"
    start_time = time.time()
    attempts = 0
    
    while time.time() - start_time < expires_in and attempts < 100:
        attempts += 1
        time.sleep(interval)
        
        result = post_form(token_url, {
            "app_id": APP_ID,
            "app_secret": APP_SECRET,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
        })
        
        if "access_token" in result:
            print("[成功] 授权完成！")
            return result.get("access_token")
        
        error = result.get("error", "")
        if error == "authorization_pending":
            print(f"  等待授权... ({attempts})")
            continue
        elif error == "slow_down":
            interval += 5
            continue
        elif error:
            print(f"[错误] {result.get('error_description', error)}")
            return None
    
    print("[超时] 授权请求超时，请重试")
    return None

def get_chat_messages(token, start_ts, end_ts):
    """获取聊天消息"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    
    # 构建带参数的 URL
    params = urllib.parse.urlencode({
        "container_id_type": "chat",
        "container_id": TARGET_CHAT_ID,
        "start_time": start_ts,
        "end_time": end_ts,
        "page_size": 50
    })
    full_url = f"{url}?{params}"
    
    req = urllib.request.Request(full_url, method="GET")
    for k, v in headers.items():
        req.add_header(k, v)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 0:
                return result.get("data", {}).get("items", [])
            else:
                print(f"  [API错误] {result.get('msg')}")
                return None
    except Exception as e:
        print(f"  [请求错误] {e}")
        return None

def format_message(msg, my_open_id=None):
    """格式化消息"""
    msg_type = msg.get("msg_type", "unknown")
    content = msg.get("body", {}).get("content", "")
    create_time = msg.get("create_time", "")
    sender = msg.get("sender", {})
    sender_id = sender.get("sender_id", {}).get("open_id", "")
    
    # 解析时间
    if create_time:
        try:
            dt = datetime.fromtimestamp(int(create_time) / 1000)
            time_str = dt.strftime("%m-%d %H:%M")
        except:
            time_str = str(create_time)
    else:
        time_str = "未知"
    
    # 判断发送者
    if sender_id == my_open_id:
        sender_name = "我"
    elif sender_id:
        sender_name = sender_id[:10]
    else:
        sender_name = "未知"
    
    # 解析内容
    try:
        content_obj = json.loads(content)
        if isinstance(content_obj, dict):
            if "text" in content_obj:
                text = content_obj["text"]
            elif msg_type == "image":
                text = "[图片]"
            elif msg_type == "file":
                text = "[文件]"
            elif msg_type == "post":
                text = "[富文本消息]"
            else:
                text = str(content_obj)[:100]
        else:
            text = str(content)[:100]
    except:
        text = str(content)[:100] if content else "[无内容]"
    
    return time_str, sender_name, msg_type, text

def send_message(token, user_id, content):
    """发送消息给用户"""
    url = f"{BASE_URL}/im/v1/messages?receive_id_type=open_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "receive_id": user_id,
        "msg_type": "text",
        "content": json.dumps({"text": content[:4900]})  # 限制长度
    }
    
    result = post_json(url, data, headers)
    return result.get("code") == 0

def main():
    print("\n" + "=" * 70)
    print(f"获取指定 chat 的聊天记录")
    print(f"chat_id: {TARGET_CHAT_ID}")
    print("=" * 70)
    
    # 计算昨天的时间范围
    yesterday = datetime.now() - timedelta(days=1)
    start_ts = int(yesterday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    end_ts = int(yesterday.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())
    
    date_str = yesterday.strftime('%Y年%m月%d日')
    print(f"\n[日期] {date_str}")
    
    # 获取 user_access_token
    print("\n[授权] 需要获取 user_access_token")
    token = get_user_token_by_device_flow()
    
    if not token:
        print("\n[失败] 无法获取授权，请重试")
        return
    
    print(f"\n[Token] {token[:30]}...")
    
    # 获取消息
    print(f"\n[获取] 正在获取聊天记录...")
    msgs = get_chat_messages(token, start_ts, end_ts)
    
    if msgs is None:
        print("[失败] 无法获取消息")
        return
    
    print(f"[成功] 共 {len(msgs)} 条消息")
    
    # 生成报告
    report_lines = [
        f"📋 聊天记录详情 ({date_str}) - 用户权限",
        "",
        f"🔑 chat_id: {TARGET_CHAT_ID}",
        f"📊 消息数: {len(msgs)} 条",
        "",
        "=" * 50,
        ""
    ]
    
    if msgs:
        msgs_sorted = sorted(msgs, key=lambda x: x.get("create_time", ""))
        for msg in msgs_sorted:
            time_str, sender, msg_type, text = format_message(msg, USER_OPEN_ID)
            report_lines.append(f"[{time_str}] {sender} ({msg_type}):")
            report_lines.append(f"  {text}")
            report_lines.append("")
    else:
        report_lines.append("该聊天昨日无消息。")
    
    report = "\n".join(report_lines)
    
    # 保存报告
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/chat_{TARGET_CHAT_ID[-12:]}_{yesterday.strftime('%Y%m%d')}_user.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n[完成] 报告已保存: {report_file}")
    
    # 发送消息
    print("\n[发送] 发送报告到飞书...")
    if send_message(token, USER_OPEN_ID, report):
        print("[成功] 消息已发送!")
    else:
        print("[失败] 发送消息失败")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
