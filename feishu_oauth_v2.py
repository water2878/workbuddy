#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书新版 OAuth 2.0 授权流程 - 获取 user_access_token
访问地址: http://localhost:8080
"""
import http.server
import socketserver
import urllib.parse
import urllib.request
import json
import webbrowser
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 应用配置
APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"
REDIRECT_URI = "http://localhost:8080/callback"

# 需要的权限（使用飞书 OAuth 标准 scope 格式）
# 参考: https://open.feishu.cn/document/common-capabilities/sso/web-application-end-user-consent/end-user-consent-overview
SCOPES = [
    "im:message:readonly",      # 读取消息
    "offline_access"            # 获取 refresh_token
]

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/":
            # 首页 - 跳转到授权页面
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
                
                if token_data and "access_token" in token_data:
                    access_token = token_data["access_token"]
                    refresh_token = token_data.get("refresh_token", "N/A")
                    expires_in = token_data.get("expires_in", "N/A")
                    
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
                        <h1 class="success">授权成功！</h1>
                        <p>请将以下 token 复制给机器人：</p>
                        
                        <h3>Access Token:</h3>
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
                    
                    # 保存到文件
                    with open("feishu_user_token.json", "w") as f:
                        json.dump(token_data, f, indent=2)
                    print("Token 已保存到 feishu_user_token.json")
                else:
                    error_msg = token_data.get("error_description", "未知错误") if token_data else "请求失败"
                    html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head><meta charset="utf-8"><title>授权失败</title></head>
                    <body>
                        <h1 style="color: red;">授权失败</h1>
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
                self.wfile.write("<h1>错误：未获取到授权码</h1>".encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def exchange_code_for_token(self, code):
        """用 code 换取 access_token"""
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
                result = json.loads(resp.read())
                if result.get("code") == 0:
                    return result["data"]
                else:
                    return {"error": result.get("msg", "未知错误")}
        except urllib.error.HTTPError as e:
            return json.loads(e.read())
    
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
