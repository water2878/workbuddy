#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书新版 OAuth 授权流程 - 获取 user_access_token
访问地址: http://localhost:8080
"""
import http.server
import socketserver
import urllib.parse
import urllib.request
import json
import webbrowser

# 应用配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
REDIRECT_URI = "http://localhost:8080/callback"

# 需要的权限 - 新版 OAuth 必须使用这些 scope
SCOPES = [
    "im:message:readonly",      # 读取消息
    "im:chat:readonly",         # 读取会话信息
    "contact:user:readonly",    # 读取用户信息
    "offline_access"            # 获取 refresh_token
]

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/":
            # 首页 - 跳转到授权页面 (使用新版 OAuth 端点)
            scope_str = "%20".join(SCOPES)
            auth_url = (
                f"https://open.feishu.cn/open-apis/authen/v1/authorize"
                f"?app_id={APP_ID}"
                f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
                f"&scope={scope_str}"
            )
            
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            
        elif parsed.path == "/callback":
            # 授权回调
            query = urllib.parse.parse_qs(parsed.query)
            code = query.get("code", [None])[0]
            
            if code:
                # 用 code 换取 token
                token_data = self.exchange_code_for_token(code)
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                
                if token_data and token_data.get("code") == 0:
                    access_token = token_data["data"]["access_token"]
                    refresh_token = token_data["data"].get("refresh_token", "N/A")
                    expires_in = token_data["data"].get("expires_in", "N/A")
                    
                    html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>授权成功</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                            .token {{ background: #f0f0f0; padding: 15px; border-radius: 5px; word-break: break-all; font-family: monospace; }}
                            .success {{ color: green; }}
                        </style>
                    </head>
                    <body>
                        <h1 class="success">✓ 授权成功！</h1>
                        <p>请将以下 token 复制给机器人：</p>
                        
                        <h3>Access Token (user_access_token):</h3>
                        <div class="token">{access_token}</div>
                        
                        <h3>Refresh Token:</h3>
                        <div class="token">{refresh_token}</div>
                        
                        <h3>过期时间:</h3>
                        <div class="token">{expires_in} 秒</div>
                        
                        <p>现在可以关闭此页面，将 Access Token 发送给机器人。</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode())
                    print("\n" + "="*60)
                    print("授权成功！")
                    print("="*60)
                    print(f"Access Token: {access_token}")
                    print(f"Refresh Token: {refresh_token}")
                    print(f"Expires In: {expires_in} 秒")
                    print("="*60 + "\n")
                else:
                    error_msg = token_data.get("msg", "未知错误") if token_data else "请求失败"
                    html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head><meta charset="utf-8"><title>授权失败</title></head>
                    <body>
                        <h1 style="color: red;">✗ 授权失败</h1>
                        <p>{error_msg}</p>
                        <p>请返回重试</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode())
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>错误：未获取到授权码</h1>")
        else:
            self.send_response(404)
            self.end_headers()
    
    def exchange_code_for_token(self, code):
        """用 code 换取 access_token (新版OAuth)"""
        url = "https://open.feishu.cn/open-apis/authen/v1/access_token"
        data = {
            "grant_type": "authorization_code",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "code": code
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"Token exchange error: {e.read().decode()}")
            return None
    
    def get_tenant_token(self):
        """获取 tenant_access_token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": APP_ID,
            "app_secret": APP_SECRET
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("tenant_access_token")
        except Exception as e:
            print(f"Get tenant token error: {e}")
            return None
    
    def log_message(self, format, *args):
        print(f"[OAuth Server] {format % args}")

def main():
    PORT = 8080
    
    print("="*60)
    print("飞书 OAuth 授权服务")
    print("="*60)
    print(f"1. 请确保应用后台配置了回调地址: http://localhost:{PORT}/callback")
    print(f"2. 访问: http://localhost:{PORT}")
    print(f"3. 用飞书扫码授权")
    print(f"4. 复制获取到的 token")
    print("="*60)
    print()
    
    # 自动打开浏览器
    webbrowser.open(f"http://localhost:{PORT}")
    
    with socketserver.TCPServer(("", PORT), OAuthHandler) as httpd:
        print(f"服务器运行在 http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
