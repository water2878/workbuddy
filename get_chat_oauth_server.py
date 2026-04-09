#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 OAuth 授权码流程获取 user_access_token，然后获取聊天记录
启动服务: python get_chat_oauth_server.py
访问: http://localhost:8080
"""

import http.server
import socketserver
import urllib.parse
import urllib.request
import json
import webbrowser
import sys
from datetime import datetime, timedelta

# 飞书配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
USER_OPEN_ID = "ou_4a86846caf437e8fda2fc9f2794c5424"
BASE_URL = "https://open.feishu.cn/open-apis"

# 指定的 chat_id
TARGET_CHAT_ID = "oc_d9e39d842488bad6ad9a45c6f31508d4"

# 计算昨天的时间
YESTERDAY = datetime.now() - timedelta(days=1)
START_TS = int(YESTERDAY.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
END_TS = int(YESTERDAY.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())

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

def get_chat_messages(token):
    """获取聊天消息"""
    url = f"{BASE_URL}/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = urllib.parse.urlencode({
        "container_id_type": "chat",
        "container_id": TARGET_CHAT_ID,
        "start_time": START_TS,
        "end_time": END_TS,
        "page_size": 50
    })
    
    req = urllib.request.Request(f"{url}?{params}", method="GET")
    for k, v in headers.items():
        req.add_header(k, v)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 0:
                return result.get("data", {}).get("items", [])
            else:
                return {"error": result.get("msg", "API错误")}
    except Exception as e:
        return {"error": str(e)}

def format_message(msg):
    """格式化消息"""
    msg_type = msg.get("msg_type", "unknown")
    content = msg.get("body", {}).get("content", "")
    create_time = msg.get("create_time", "")
    
    if create_time:
        try:
            dt = datetime.fromtimestamp(int(create_time) / 1000)
            time_str = dt.strftime("%m-%d %H:%M")
        except:
            time_str = str(create_time)
    else:
        time_str = "未知"
    
    sender = msg.get("sender", {}).get("sender_id", {}).get("open_id", "未知")[:10]
    
    try:
        content_obj = json.loads(content)
        if isinstance(content_obj, dict) and "text" in content_obj:
            text = content_obj["text"]
        elif msg_type == "image":
            text = "[图片]"
        elif msg_type == "file":
            text = "[文件]"
        else:
            text = str(content)[:100]
    except:
        text = str(content)[:100] if content else "[无内容]"
    
    return time_str, sender, msg_type, text

def send_report(token, messages):
    """生成并发送报告"""
    date_str = YESTERDAY.strftime('%Y年%m月%d日')
    
    report_lines = [
        f"📋 聊天记录详情 ({date_str})",
        "",
        f"🔑 chat_id: {TARGET_CHAT_ID}",
        f"📊 消息数: {len(messages)} 条",
        "",
        "=" * 50,
        ""
    ]
    
    if messages:
        msgs_sorted = sorted(messages, key=lambda x: x.get("create_time", ""))
        for msg in msgs_sorted:
            time_str, sender, msg_type, text = format_message(msg)
            report_lines.append(f"[{time_str}] {sender} ({msg_type}):")
            report_lines.append(f"  {text}")
            report_lines.append("")
    else:
        report_lines.append("该聊天昨日无消息。")
    
    report = "\n".join(report_lines)
    
    # 保存到文件
    report_file = f"C:/Users/Lenovo/WorkBuddy/Claw/chat_{TARGET_CHAT_ID[-12:]}_{YESTERDAY.strftime('%Y%m%d')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[文件] 报告已保存: {report_file}")
    
    # 发送到飞书
    url = f"{BASE_URL}/im/v1/messages?receive_id_type=open_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "receive_id": USER_OPEN_ID,
        "msg_type": "text",
        "content": json.dumps({"text": report[:4900]})
    }
    
    result = post_json(url, data, headers)
    if result.get("code") == 0:
        print("[发送] 报告已发送到飞书")
        return True
    else:
        print(f"[发送失败] {result.get('msg', '未知错误')}")
        return False

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/":
            # 跳转到授权页面
            auth_url = (
                f"https://open.feishu.cn/open-apis/authen/v1/authorize"
                f"?app_id={APP_ID}"
                f"&redirect_uri=http://localhost:8080/callback"
                f"&scope=im:message:readonly im:chat:readonly"
            )
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            
        elif parsed.path == "/callback":
            query = urllib.parse.parse_qs(parsed.query)
            code = query.get("code", [None])[0]
            
            if code:
                # 换取 token
                token_data = self.exchange_code(code)
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                
                if token_data and "access_token" in token_data:
                    token = token_data["access_token"]
                    
                    # 获取聊天记录
                    print(f"\n[Token] 获取成功: {token[:30]}...")
                    print("[获取] 正在获取聊天记录...")
                    messages = get_chat_messages(token)
                    
                    if isinstance(messages, dict) and "error" in messages:
                        error_msg = messages["error"]
                        html = f"""
                        <h1 style="color: red;">获取失败</h1>
                        <p>{error_msg}</p>
                        """
                        self.wfile.write(html.encode())
                    else:
                        print(f"[成功] 获取到 {len(messages)} 条消息")
                        send_report(token, messages)
                        
                        html = f"""
                        <!DOCTYPE html>
                        <html>
                        <head><meta charset="utf-8"><title>完成</title></head>
                        <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
                            <h1 style="color: green;">✅ 完成！</h1>
                            <p>已获取 {len(messages)} 条消息</p>
                            <p>报告已发送到你的飞书</p>
                            <hr>
                            <p><b>Token:</b> <span style="font-family: monospace; background: #f0f0f0; padding: 5px;">{token}</span></p>
                            <p>可以关闭此页面了</p>
                        </body>
                        </html>
                        """
                        self.wfile.write(html.encode())
                        
                        # 保存 token
                        with open("feishu_token.json", "w") as f:
                            json.dump(token_data, f, indent=2)
                        print("[保存] Token 已保存到 feishu_token.json")
                else:
                    error = token_data.get("error", "未知错误") if token_data else "请求失败"
                    html = f"<h1 style='color: red;'>授权失败</h1><p>{error}</p>"
                    self.wfile.write(html.encode())
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h1>错误：未获取到授权码</h1>".encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def exchange_code(self, code):
        """用 code 换取 access_token"""
        url = f"{BASE_URL}/authen/v1/access_token"
        data = {
            "grant_type": "authorization_code",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "code": code
        }
        result = post_json(url, data)
        if result.get("code") == 0:
            return result.get("data", {})
        return {"error": result.get("msg", "未知错误")}
    
    def log_message(self, format, *args):
        print(f"[Server] {format % args}")

def main():
    PORT = 8080
    
    print("=" * 70)
    print("飞书 OAuth 授权 - 获取聊天记录")
    print("=" * 70)
    print(f"\n目标 chat_id: {TARGET_CHAT_ID}")
    print(f"查询日期: {YESTERDAY.strftime('%Y年%m月%d日')}")
    print(f"\n1. 访问: http://localhost:{PORT}")
    print("2. 用飞书扫码授权")
    print("3. 等待自动获取聊天记录")
    print("=" * 70 + "\n")
    
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except:
        pass
    
    with socketserver.TCPServer(("", PORT), OAuthHandler) as httpd:
        print(f"服务器运行在 http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
