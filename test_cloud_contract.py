#!/usr/bin/env python3
"""
测试云端合同同步和审批通知
"""
import os
import sys
import json
import requests
import time

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

CLOUD_SERVER = os.environ.get("CLOUD_SERVER", "http://120.26.84.224:5032")
CLOUD_TOKEN = os.environ.get("CLOUD_TOKEN", "changteng2026")
SALES_ID = os.environ.get("SALES_ID", "lisheng")

def test_sync_contract():
    """测试推送合同到云端"""
    print("=" * 50)
    print("测试1: 推送合同到云端")
    print("=" * 50)
    
    payload = {
        "customer_name": "测试公司",
        "customer_contact": "张三",
        "customer_phone": "13800138000",
        "customer_address": "广州市天河区测试路123号",
        "products": [
            {
                "name": "智能升降桌",
                "model": "T423",
                "quantity": 5,
                "unit_price": 1000,
                "subtotal": 5000
            }
        ],
        "order_no": f"TEST{int(time.time())}",
        "order_date": "2026-05-12",
        "delivery_date": "2026-05-20",
        "payment_terms": "银行转账",
        "voltage": "220V/50Hz",
        "plug_type": "国标",
        "shipping_country": "中国",
        "notes": "测试合同",
        "session_id": "test_session_123",
        "customer_wxid": "test_wxid",
        "customer_nickname": "测试客户",
        "agent_id": SALES_ID,  # 关键字段
    }
    
    headers = {"Content-Type": "application/json"}
    if CLOUD_TOKEN:
        headers["Authorization"] = f"Bearer {CLOUD_TOKEN}"
    
    try:
        resp = requests.post(
            f"{CLOUD_SERVER}/api/contracts/sync",
            json=payload,
            headers=headers,
            timeout=30
        )
        print(f"状态码: {resp.status_code}")
        print(f"响应: {resp.text}")
        
        if resp.status_code == 200:
            data = resp.json()
            contract_id = data.get("contract_id")
            print(f"✓ 合同创建成功: {contract_id}")
            return contract_id
        else:
            print(f"✗ 合同创建失败")
            return None
    except Exception as e:
        print(f"✗ 异常: {e}")
        return None

def test_check_contract(contract_id):
    """检查云端合同数据"""
    print("\n" + "=" * 50)
    print("测试2: 检查云端合同数据")
    print("=" * 50)
    
    try:
        # 使用 detail 接口获取单个合同
        resp = requests.get(
            f"{CLOUD_SERVER}/api/contracts/detail/{contract_id}",
            headers={"Authorization": f"Bearer {CLOUD_TOKEN}"} if CLOUD_TOKEN else {},
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            contract = data.get("contract", {})
            print(f"合同ID: {contract.get('id')}")
            print(f"agent_id: {contract.get('agent_id', '未设置')}")
            print(f"状态: {contract.get('status')}")
            print(f"客户: {contract.get('customer_nickname')}")
            return contract
        else:
            print(f"✗ 查询失败: {resp.status_code}")
            print(f"响应: {resp.text[:200]}")
    except Exception as e:
        print(f"✗ 异常: {e}")
    return None

def test_approve_contract(contract_id):
    """测试审批合同"""
    print("\n" + "=" * 50)
    print("测试3: 审批合同")
    print("=" * 50)
    
    headers = {"Content-Type": "application/json"}
    if CLOUD_TOKEN:
        headers["Authorization"] = f"Bearer {CLOUD_TOKEN}"
    
    try:
        resp = requests.post(
            f"{CLOUD_SERVER}/api/contracts/approve",
            json={"contract_id": contract_id, "approver": "测试审批人"},
            headers=headers,
            timeout=10
        )
        
        print(f"状态码: {resp.status_code}")
        print(f"响应: {resp.text}")
        
        if resp.status_code == 200:
            print(f"✓ 合同审批成功")
            return True
        else:
            print(f"✗ 审批失败")
            return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False

def test_agent_sse():
    """测试 SSE 连接"""
    print("\n" + "=" * 50)
    print("测试4: 测试 SSE 连接")
    print("=" * 50)
    
    import socket
    
    try:
        m = requests.utils.urlparse(CLOUD_SERVER)
        host = m.hostname
        port = m.port or 5032
        
        print(f"连接 {host}:{port}...")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        auth = f"Bearer {CLOUD_TOKEN}" if CLOUD_TOKEN else ""
        req = (
            f"GET /api/contracts/agent-events?agent={SALES_ID} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Accept: text/event-stream\r\n"
            f"Cache-Control: no-cache\r\n"
            f"Connection: keep-alive\r\n"
            f"Authorization: {auth}\r\n"
            f"\r\n"
        )
        sock.sendall(req.encode())
        
        # 接收响应头
        sock.settimeout(5)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(1024)
            if not chunk:
                break
            response += chunk
        
        print(f"响应头:\n{response.decode()[:500]}")
        
        # 尝试接收一条消息
        sock.settimeout(10)
        try:
            data = sock.recv(4096)
            if data:
                print(f"收到数据: {data.decode()[:500]}")
        except socket.timeout:
            print("等待消息超时（正常，等待审批通知）")
        
        sock.close()
        print("✓ SSE 连接测试完成")
        return True
        
    except Exception as e:
        print(f"✗ SSE 连接失败: {e}")
        return False

def main():
    print("云端合同同步测试")
    print(f"云端服务器: {CLOUD_SERVER}")
    print(f"SALES_ID: {SALES_ID}")
    print()
    
    # 测试1: 推送合同
    contract_id = test_sync_contract()
    if not contract_id:
        print("\n✗ 测试失败: 无法创建合同")
        return
    
    # 等待一下
    time.sleep(1)
    
    # 测试2: 检查合同
    contract = test_check_contract(contract_id)
    if not contract:
        print("\n✗ 测试失败: 无法查询合同")
        return
    
    # 检查 agent_id
    agent_id = contract.get('agent_id')
    if not agent_id:
        print("\n⚠ 警告: 合同 agent_id 为空！")
        print("这就是本地接收不到通知的原因！")
    else:
        print(f"\n✓ 合同 agent_id 正确: {agent_id}")
    
    # 测试3: 审批合同
    input("\n按回车键继续审批合同...")
    if test_approve_contract(contract_id):
        print("\n请在云端查看合同是否已审批，并检查本地是否收到通知")
    
    # 测试4: SSE 连接
    input("\n按回车键测试 SSE 连接...")
    test_agent_sse()
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

if __name__ == "__main__":
    main()
