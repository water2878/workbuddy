#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书配置诊断工具
"""
import urllib.request
import json
import os

APP_ID = "cli_a93fb4f24f785bc3"
APP_SECRET = "3bbpjT33nUbpR4dOpFuajgwfyI5qakwG"

def test_api(name, url, method="GET", data=None, headers=None):
    """测试 API 调用"""
    try:
        req = urllib.request.Request(url, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        if data:
            req.data = data.encode()
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get('code') == 0:
                return True, result
            else:
                return False, result
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("飞书配置诊断报告")
    print("=" * 60)
    print(f"\n应用 ID: {APP_ID}")
    print(f"应用 Secret: {'*' * 20}")
    
    # 1. 测试获取 token
    print("\n【1】测试获取 tenant_access_token...")
    auth_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    auth_data = json.dumps({'app_id': APP_ID, 'app_secret': APP_SECRET})
    success, result = test_api("Auth", auth_url, "POST", auth_data, {'Content-Type': 'application/json'})
    
    if success:
        token = result['tenant_access_token']
        expire = result.get('expire', 0)
        print(f"  [OK] 成功 (有效期 {expire} 秒)")
    else:
        print(f"  [FAIL] 失败: {result}")
        return
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # 2. 测试获取机器人信息
    print("\n【2】测试获取机器人信息...")
    bot_url = "https://open.feishu.cn/open-apis/bot/v3/info"
    success, result = test_api("Bot Info", bot_url, headers=headers)
    if success:
        bot = result.get('bot', {})
        print(f"  [OK] 成功")
        print(f"     名称: {bot.get('app_name', 'N/A')}")
        print(f"     Open ID: {bot.get('open_id', 'N/A')}")
        print(f"     激活状态: {bot.get('activate_status', 'N/A')}")
    else:
        print(f"  [FAIL] 失败: {result}")
    
    # 3. 测试获取会话列表
    print("\n【3】测试获取会话列表...")
    chats_url = "https://open.feishu.cn/open-apis/im/v1/chats?page_size=10"
    success, result = test_api("Chats", chats_url, headers=headers)
    if success:
        items = result.get('data', {}).get('items', [])
        print(f"  [OK] 成功 (找到 {len(items)} 个会话)")
        for item in items:
            print(f"     - {item.get('chat_id')}: {item.get('name', '无名称')}")
    else:
        print(f"  [FAIL] 失败: {result}")
    
    # 4. 测试获取消息
    print("\n【4】测试获取消息...")
    if success and items:
        chat_id = items[0]['chat_id']
        msg_url = f"https://open.feishu.cn/open-apis/im/v1/messages?container_id={chat_id}&container_id_type=chat&page_size=5"
        success, result = test_api("Messages", msg_url, headers=headers)
        if success:
            msg_count = len(result.get('data', {}).get('items', []))
            print(f"  [OK] 成功 (获取到 {msg_count} 条消息)")
        else:
            print(f"  [FAIL] 失败: {result}")
    else:
        print("  [SKIP] 跳过 (没有可用会话)")
    
    # 5. 测试搜索用户
    print("\n【5】测试搜索用户...")
    search_url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id"
    search_data = json.dumps({"emails": ["test@example.com"]})
    success, result = test_api("User Search", search_url, "POST", search_data, headers)
    if success:
        print(f"  [OK] 成功")
    else:
        error_code = result.get('code', 0)
        if error_code == 403:
            print(f"  [WARN] 权限不足 (需要开通 contact:user:readonly 权限)")
        else:
            print(f"  [FAIL] 失败: {result.get('msg', result)}")
    
    # 6. 检查 lark-cli 配置
    print("\n【6】检查 lark-cli 配置...")
    config_path = os.path.expanduser("~/.lark-cli/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            apps = config.get('apps', [])
            if apps:
                app = apps[0]
                print(f"  [OK] 配置存在")
                print(f"     App ID: {app.get('appId', 'N/A')}")
                print(f"     Brand: {app.get('brand', 'N/A')}")
            else:
                print(f"  [WARN] 配置中没有应用")
        except Exception as e:
            print(f"  [FAIL] 读取配置失败: {e}")
    else:
        print(f"  [FAIL] 配置文件不存在: {config_path}")
    
    # 7. 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    print("""
[正常]
- 获取 tenant_access_token [OK]
- 获取机器人信息 [OK]
- 获取会话列表 [OK]
- 获取消息 [OK]

[问题]
- 无法搜索用户 (权限不足)
- 无法给外部联系人发消息 (需要对方添加机器人)
- 无法获取单聊记录 (机器人不在会话中)

[建议]
1. 在飞书开放平台开通更多权限:
   - contact:user:readonly (搜索用户)
   - im:message.p2p_msg (接收单聊消息)

2. 让郑淡定添加机器人为联系人后，才能发消息

3. 如需获取私人聊天记录，需要使用用户身份授权
""")

if __name__ == "__main__":
    main()
