"""
客户无忧信息推送审批 API 模块
提供客户信息推送的云端审批功能
"""
import os
import json
import uuid
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote

# 添加 core 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ═══════════════════════════════════════════════════════
# 日志工具
# ═══════════════════════════════════════════════════════
def log(msg, tag="客户"):
    """统一日志输出，带时间戳"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{tag}] {msg}", flush=True)

# 配置
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CUSTOMERS_DATA_DIR = os.path.join(BASE_DIR, "data", "customers")
os.makedirs(CUSTOMERS_DATA_DIR, exist_ok=True)

# 数据文件
PENDING_FILE = os.path.join(CUSTOMERS_DATA_DIR, "pending.json")
APPROVED_FILE = os.path.join(CUSTOMERS_DATA_DIR, "approved.json")
SENT_FILE = os.path.join(CUSTOMERS_DATA_DIR, "sent.json")


def _load_json(filepath, default=None):
    """加载 JSON 文件"""
    if default is None:
        default = []
    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except Exception as e:
            log(f"加载 JSON 失败 {filepath}: {e}", "ERROR")
            pass
    return default


def _save_json(filepath, data):
    """保存 JSON 文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def handle_request(handler, method, path):
    """处理客户无忧 API 请求
    
    Args:
        handler: HTTPRequestHandler 实例
        method: HTTP 方法 (GET, POST)
        path: 请求路径
        
    Returns:
        bool: 是否处理了该请求
    """
    # 获取查询参数
    from urllib.parse import urlparse
    parsed = urlparse(path)
    query_params = parse_qs(parsed.query)
    agent_id = query_params.get('agent_id', [None])[0]
    
    # 分页参数
    try:
        page = int(query_params.get('page', [1])[0])
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = int(query_params.get('page_size', [10])[0])
    except (ValueError, TypeError):
        page_size = 10
    # 限制最大页大小
    page_size = min(page_size, 100)
    
    # GET 请求
    if method == "GET":
        # 处理 /api/customers?status=xxx 格式的请求
        if path == "/api/customers" or path.startswith("/api/customers?"):
            status_filter = query_params.get('status', ['pending'])[0]
            if status_filter == 'pending':
                _handle_get_pending(handler, agent_id, page, page_size)
            elif status_filter == 'approved':
                _handle_get_approved(handler, agent_id, page, page_size)
            elif status_filter == 'sent':
                _handle_get_sent(handler, agent_id, page, page_size)
            else:
                _handle_get_pending(handler, agent_id, page, page_size)
            return True
        elif path.startswith("/api/customers/pending"):
            _handle_get_pending(handler, agent_id, page, page_size)
            return True
        elif path.startswith("/api/customers/approved"):
            _handle_get_approved(handler, agent_id, page, page_size)
            return True
        elif path.startswith("/api/customers/sent"):
            _handle_get_sent(handler, agent_id, page, page_size)
            return True
        elif path.startswith("/api/customers/detail/"):
            record_id = path.split("/")[-1]
            _handle_get_detail(handler, record_id)
            return True
        elif path == "/api/customers/stats":
            _handle_get_stats(handler)
            return True
        elif path.startswith("/api/customers/update/"):
            record_id = path.split("/")[-1]
            _handle_update_customer(handler, record_id)
            return True
        elif path == "/api/customers/agents":
            _handle_get_agents(handler)
            return True
    
    # POST 请求
    if method == "POST":
        if path.startswith("/api/customers/approve/"):
            record_id = path.split("/")[-1]
            _handle_approve(handler, record_id)
            return True
        elif path.startswith("/api/customers/reject/"):
            record_id = path.split("/")[-1]
            _handle_reject(handler, record_id)
            return True
        elif path.startswith("/api/customers/send/"):
            record_id = path.split("/")[-1]
            _handle_send(handler, record_id)
            return True
        elif path.startswith("/push/"):
            # 兼容前端调用的 /push/ 路由
            record_id = path.split("/")[-1]
            _handle_push_to_crm(handler, record_id)
            return True
        elif path == "/api/customers/batch-push":
            # 批量推送到客户无忧CRM
            _handle_batch_push_to_crm(handler)
            return True
        elif path == "/api/customers/push-by-agent":
            # 按业务员推送到客户无忧CRM
            _handle_push_by_agent(handler)
            return True
        elif path == "/api/customers/sync":
            _handle_sync(handler)
            return True
        elif path == "/api/customers/push-profiles-to-cloud":
            # 推送本地客户画像到云端审批系统
            _handle_push_profiles_to_cloud(handler)
            return True
        elif path == "/api/customers/check":
            # 检查客户是否已存在于云端
            _handle_check_customer_exists(handler)
            return True
    
    return False


def _send_json(handler, data, status_code=200):
    """发送 JSON 响应"""
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


def _paginate_data(data, page, page_size):
    """分页处理数据"""
    total = len(data)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    return {
        'data': data[start:end],
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages
        }
    }


def _handle_get_pending(handler, agent_id=None, page=1, page_size=10):
    """获取待审批列表"""
    data = _load_json(PENDING_FILE, [])
    # 按 agent_id 筛选
    if agent_id:
        data = [r for r in data if r.get('agent_id') == agent_id or r.get('sales_id') == agent_id]
    result = _paginate_data(data, page, page_size)
    _send_json(handler, result)


def _handle_get_approved(handler, agent_id=None, page=1, page_size=10):
    """获取已审批列表"""
    data = _load_json(APPROVED_FILE, [])
    # 按 agent_id 筛选
    if agent_id:
        data = [r for r in data if r.get('agent_id') == agent_id or r.get('sales_id') == agent_id]
    result = _paginate_data(data, page, page_size)
    _send_json(handler, result)


def _handle_get_sent(handler, agent_id=None, page=1, page_size=10):
    """获取已发送列表"""
    data = _load_json(SENT_FILE, [])
    # 按 agent_id 筛选
    if agent_id:
        data = [r for r in data if r.get('agent_id') == agent_id or r.get('sales_id') == agent_id]
    result = _paginate_data(data, page, page_size)
    _send_json(handler, result)


def _handle_get_detail(handler, record_id):
    """获取记录详情"""
    # 在所有列表中查找
    for filepath in [PENDING_FILE, APPROVED_FILE, SENT_FILE]:
        data = _load_json(filepath, [])
        for record in data:
            if record.get('id') == record_id or record.get('record_id') == record_id:
                _send_json(handler, {"success": True, "data": record})
                return
    
    _send_json(handler, {"success": False, "error": "记录不存在"}, 404)


def _handle_approve(handler, record_id):
    """审批通过"""
    try:
        pending = _load_json(PENDING_FILE, [])
        approved = _load_json(APPROVED_FILE, [])
        
        # 查找记录
        record = None
        for i, r in enumerate(pending):
            if r.get('id') == record_id or r.get('record_id') == record_id:
                record = pending.pop(i)
                break
        
        if not record:
            _send_json(handler, {"success": False, "error": "记录不存在"}, 404)
            return
        
        # 更新状态
        record['status'] = 'approved'
        record['approved_at'] = datetime.now().isoformat()
        record['approved_by'] = '云端审批'
        
        # 添加到已审批列表
        approved.insert(0, record)
        
        # 保存
        _save_json(PENDING_FILE, pending)
        _save_json(APPROVED_FILE, approved)
        
        _send_json(handler, {"success": True, "message": "审批通过", "data": record})
        
    except Exception as e:
        log(f"审批失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_reject(handler, record_id):
    """拒绝"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)
        reason = params.get('reason', '')
        
        pending = _load_json(PENDING_FILE, [])
        
        # 查找记录
        record = None
        for i, r in enumerate(pending):
            if r.get('id') == record_id or r.get('record_id') == record_id:
                record = pending.pop(i)
                break
        
        if not record:
            _send_json(handler, {"success": False, "error": "记录不存在"}, 404)
            return
        
        # 更新状态
        record['status'] = 'rejected'
        record['rejected_at'] = datetime.now().isoformat()
        record['reject_reason'] = reason
        
        # 保存
        _save_json(PENDING_FILE, pending)
        
        _send_json(handler, {"success": True, "message": "已拒绝", "data": record})
        
    except Exception as e:
        log(f"拒绝失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_send(handler, record_id):
    """推送客户信息到微信"""
    try:
        # 读取请求体（可选的消息内容）
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)
        custom_message = params.get('message', '')
        
        approved = _load_json(APPROVED_FILE, [])
        sent = _load_json(SENT_FILE, [])
        
        # 查找记录
        record = None
        record_index = -1
        for i, r in enumerate(approved):
            if r.get('id') == record_id or r.get('record_id') == record_id:
                record = r
                record_index = i
                break
        
        if not record:
            _send_json(handler, {"success": False, "error": "记录不存在或尚未审批"}, 404)
            return
        
        # 从已审批列表移除
        approved.pop(record_index)
        
        # 更新状态
        record['status'] = 'sent'
        record['sent_at'] = datetime.now().isoformat()
        record['sent_message'] = custom_message
        
        # 添加到已发送列表
        sent.insert(0, record)
        
        # 保存
        _save_json(APPROVED_FILE, approved)
        _save_json(SENT_FILE, sent)
        
        # 这里可以添加实际的微信推送逻辑
        # 例如调用微信API发送消息给客户
        customer_id = record.get('customer_id', '')
        customer_name = record.get('cus_name', record.get('customer_nickname', '客户'))
        log(f"已向客户 {customer_name}({customer_id}) 推送信息")
        
        _send_json(handler, {"success": True, "message": "推送成功", "data": record})
        
    except Exception as e:
        log(f"推送失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_push_to_crm(handler, record_id):
    """推送客户信息到客户无忧CRM系统"""
    try:
        # 读取请求体（可选配置）
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)
        
        approved = _load_json(APPROVED_FILE, [])
        sent = _load_json(SENT_FILE, [])
        
        # 查找记录
        record = None
        record_index = -1
        for i, r in enumerate(approved):
            if r.get('id') == record_id or r.get('record_id') == record_id:
                record = r
                record_index = i
                break
        
        if not record:
            _send_json(handler, {"success": False, "error": "记录不存在或尚未审批"}, 404)
            return
        
        # 准备推送到客户无忧CRM的数据
        crm_data = {
            "cus_name": record.get('cus_name', ''),
            "mobile_phone": record.get('mobile_phone', ''),
            "work_name": record.get('work_name', ''),
            "work_address": record.get('work_address', ''),
            "email": record.get('email', ''),
            "cus_intro": record.get('cus_intro', ''),
            "get_time": record.get('get_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "industry": record.get('industry', ''),
            "source": record.get('source', '微信'),
            "agent_id": record.get('agent_id', ''),
        }
        
        # TODO: 这里添加实际的客户无忧CRM API调用
        # 示例：调用客户无忧的API接口
        # import requests
        # response = requests.post(
        #     "https://api.kehuwuyou.com/v1/customers",
        #     json=crm_data,
        #     headers={"Authorization": "Bearer YOUR_API_KEY"}
        # )
        # if response.status_code != 200:
        #     raise Exception(f"CRM API错误: {response.text}")
        
        # 模拟推送成功
        log(f"客户 {crm_data['cus_name']} 已推送到客户无忧系统", "CRM推送")
        
        # 从已审批列表移除
        approved.pop(record_index)
        
        # 更新状态
        record['status'] = 'sent'
        record['sent_at'] = datetime.now().isoformat()
        record['pushed_to_crm'] = True
        record['crm_data'] = crm_data
        
        # 添加到已发送列表
        sent.insert(0, record)
        
        # 保存
        _save_json(APPROVED_FILE, approved)
        _save_json(SENT_FILE, sent)
        
        _send_json(handler, {
            "success": True, 
            "message": "已成功推送到客户无忧系统", 
            "data": record
        })
        
    except Exception as e:
        log(f"推送到CRM失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_batch_push_to_crm(handler):
    """批量推送客户信息到客户无忧CRM系统"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)
        
        record_ids = params.get('ids', [])
        if not record_ids or not isinstance(record_ids, list):
            _send_json(handler, {"success": False, "error": "请提供要推送的客户ID列表"}, 400)
            return
        
        approved = _load_json(APPROVED_FILE, [])
        sent = _load_json(SENT_FILE, [])
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        pushed_records = []
        
        # 从后向前遍历，避免删除时索引变化
        for i in range(len(approved) - 1, -1, -1):
            record = approved[i]
            record_id = record.get('id') or record.get('record_id')
            
            if record_id in record_ids:
                try:
                    # 准备推送到客户无忧CRM的数据
                    crm_data = {
                        "cus_name": record.get('cus_name', ''),
                        "mobile_phone": record.get('mobile_phone', ''),
                        "work_name": record.get('work_name', ''),
                        "work_address": record.get('work_address', ''),
                        "email": record.get('email', ''),
                        "cus_intro": record.get('cus_intro', ''),
                        "get_time": record.get('get_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        "industry": record.get('industry', ''),
                        "source": record.get('source', '微信'),
                        "agent_id": record.get('agent_id', ''),
                    }
                    
                    # TODO: 这里添加实际的客户无忧CRM API调用
                    log(f"客户 {crm_data['cus_name']} 已推送到客户无忧系统", "CRM批量推送")
                    
                    # 从已审批列表移除
                    approved.pop(i)
                    
                    # 更新状态
                    record['status'] = 'sent'
                    record['sent_at'] = datetime.now().isoformat()
                    record['pushed_to_crm'] = True
                    record['crm_data'] = crm_data
                    
                    # 添加到已发送列表
                    sent.insert(0, record)
                    pushed_records.append(record)
                    success_count += 1
                    
                except Exception as e:
                    log(f"推送客户 {record_id} 失败: {e}", "ERROR")
                    failed_count += 1
                    failed_ids.append(record_id)
        
        # 保存
        _save_json(APPROVED_FILE, approved)
        _save_json(SENT_FILE, sent)
        
        _send_json(handler, {
            "success": True,
            "message": f"批量推送完成：成功 {success_count} 条，失败 {failed_count} 条",
            "data": {
                "success_count": success_count,
                "failed_count": failed_count,
                "failed_ids": failed_ids,
                "pushed_records": pushed_records
            }
        })
        
    except Exception as e:
        log(f"批量推送到CRM失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_push_by_agent(handler):
    """按业务员推送客户到客户无忧CRM"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)
        
        agent_id = params.get('agent_id')
        customer_ids = params.get('customer_ids', [])
        
        if not agent_id:
            _send_json(handler, {"success": False, "error": "请提供业务员ID"}, 400)
            return
        
        if not customer_ids or not isinstance(customer_ids, list):
            _send_json(handler, {"success": False, "error": "请提供要推送的客户ID列表"}, 400)
            return
        
        approved = _load_json(APPROVED_FILE, [])
        sent = _load_json(SENT_FILE, [])
        
        success_count = 0
        pushed_customers = []
        
        # 从后向前遍历，避免删除时索引变化
        for i in range(len(approved) - 1, -1, -1):
            record = approved[i]
            record_id = record.get('id') or record.get('record_id')
            record_agent = record.get('agent_id') or record.get('sales_id')
            
            # 只推送指定业务员的客户
            if record_id in customer_ids and record_agent == agent_id:
                try:
                    # 准备推送到客户无忧CRM的数据
                    crm_data = {
                        "cus_name": record.get('cus_name', ''),
                        "mobile_phone": record.get('mobile_phone', ''),
                        "work_name": record.get('work_name', ''),
                        "work_address": record.get('work_address', ''),
                        "email": record.get('email', ''),
                        "cus_intro": record.get('cus_intro', ''),
                        "get_time": record.get('get_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        "industry": record.get('industry', ''),
                        "source": record.get('source', '微信'),
                        "agent_id": agent_id,
                    }
                    
                    # TODO: 这里添加实际的客户无忧CRM API调用
                    log(f"业务员:{agent_id} 客户:{crm_data['cus_name']} 已推送", "CRM按业务员推送")
                    
                    # 从已审批列表移除
                    approved.pop(i)
                    
                    # 更新状态
                    record['status'] = 'sent'
                    record['sent_at'] = datetime.now().isoformat()
                    record['pushed_to_crm'] = True
                    record['crm_data'] = crm_data
                    
                    # 添加到已发送列表
                    sent.insert(0, record)
                    pushed_customers.append(crm_data['cus_name'])
                    success_count += 1
                    
                except Exception as e:
                    log(f"推送客户 {record_id} 失败: {e}", "ERROR")
        
        # 保存
        _save_json(APPROVED_FILE, approved)
        _save_json(SENT_FILE, sent)
        
        _send_json(handler, {
            "success": True,
            "message": f"业务员「{agent_id}」的 {success_count} 个客户已成功推送到客户无忧系统",
            "data": {
                "agent_id": agent_id,
                "success_count": success_count,
                "pushed_customers": pushed_customers
            }
        })
        
    except Exception as e:
        log(f"按业务员推送到CRM失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_sync(handler):
    """同步数据（从本地推送到云端）"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        data = json.loads(body)
        
        record = data.get('record', data)
        status = data.get('status', 'pending')
        
        # 生成 ID
        if 'id' not in record and 'record_id' not in record:
            record['id'] = str(uuid.uuid4())[:8]
        
        record['sync_at'] = datetime.now().isoformat()
        record['status'] = status
        
        # 获取记录的唯一标识（用于去重）
        record_id = record.get('id') or record.get('record_id')
        customer_phone = record.get('mobile_phone') or record.get('customer_phone') or record.get('phone')
        customer_wxid = record.get('customer_wxid') or record.get('wxid') or record.get('customer_id')
        
        # 根据状态保存到不同文件
        if status == 'pending':
            pending = _load_json(PENDING_FILE, [])
            # 检查是否已存在（根据 id、手机号或 wxid）
            exists = False
            for i, existing in enumerate(pending):
                # 检查各种可能的字段名
                existing_wxid = (existing.get('customer_wxid') or existing.get('wxid') or 
                                existing.get('customer_id') or existing.get('id'))
                existing_phone = (existing.get('mobile_phone') or existing.get('customer_phone') or 
                                 existing.get('phone'))
                
                if (existing.get('id') == record_id or 
                    existing.get('record_id') == record_id or
                    (customer_phone and existing_phone == customer_phone) or
                    (customer_wxid and existing_wxid == customer_wxid)):
                    # 更新已存在的记录
                    pending[i] = record
                    exists = True
                    log(f"更新已存在的客户记录: {record.get('cus_name', '未知')} (ID: {record_id}, wxid: {customer_wxid}, phone: {customer_phone})")
                    break
            if not exists:
                pending.insert(0, record)
                log(f"添加新客户记录: {record.get('cus_name', '未知')} (ID: {record_id})")
            _save_json(PENDING_FILE, pending)
        elif status == 'approved':
            approved = _load_json(APPROVED_FILE, [])
            # 同样检查去重
            exists = False
            for i, existing in enumerate(approved):
                if (existing.get('id') == record_id or 
                    existing.get('record_id') == record_id):
                    approved[i] = record
                    exists = True
                    break
            if not exists:
                approved.insert(0, record)
            _save_json(APPROVED_FILE, approved)
        elif status == 'sent':
            sent = _load_json(SENT_FILE, [])
            # 同样检查去重
            exists = False
            for i, existing in enumerate(sent):
                if (existing.get('id') == record_id or 
                    existing.get('record_id') == record_id):
                    sent[i] = record
                    exists = True
                    break
            if not exists:
                sent.insert(0, record)
            _save_json(SENT_FILE, sent)
        
        _send_json(handler, {"success": True, "message": "同步成功", "data": record})
        
    except Exception as e:
        log(f"同步失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_get_stats(handler):
    """获取各状态客户数量统计"""
    try:
        pending = _load_json(PENDING_FILE, [])
        approved = _load_json(APPROVED_FILE, [])
        sent = _load_json(SENT_FILE, [])
        
        stats = {
            "pending": len(pending),
            "approved": len(approved),
            "sent": len(sent)
        }
        
        _send_json(handler, {
            "success": True,
            "data": stats
        })
        
    except Exception as e:
        log(f"获取统计失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_update_customer(handler, record_id):
    """更新客户信息"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        data = json.loads(body)
        
        log(f"更新客户 ID: {record_id}, 数据: {data}")
        
        # 在所有文件中查找客户
        files_to_check = [
            (PENDING_FILE, "pending"),
            (APPROVED_FILE, "approved"),
            (SENT_FILE, "sent")
        ]
        
        for filepath, status in files_to_check:
            records = _load_json(filepath, [])
            for i, record in enumerate(records):
                record_ids = [
                    record.get("id"),
                    record.get("record_id"),
                    record.get("customer_id"),
                    record.get("_id")
                ]
                if record_id in [str(x) for x in record_ids if x]:
                    # 更新字段
                    if "cus_name" in data:
                        record["cus_name"] = data["cus_name"]
                        record["customer_name"] = data["cus_name"]
                    if "mobile_phone" in data:
                        record["mobile_phone"] = data["mobile_phone"]
                        record["phone"] = data["mobile_phone"]
                        record["customer_phone"] = data["mobile_phone"]
                    if "work_name" in data:
                        record["work_name"] = data["work_name"]
                        record["company"] = data["work_name"]
                        record["work_address"] = data["work_name"]
                    if "cus_intro" in data:
                        record["cus_intro"] = data["cus_intro"]
                        record["content"] = data["cus_intro"]
                        record["notes"] = data["cus_intro"]
                    
                    # 更新时间戳
                    record["updated_at"] = datetime.now().isoformat()
                    
                    # 保存
                    _save_json(filepath, records)
                    
                    log(f"更新客户成功: {record_id}")
                    _send_json(handler, {
                        "success": True,
                        "message": "客户信息已更新",
                        "data": record
                    })
                    return
        
        # 未找到客户
        log(f"更新客户未找到: {record_id}", "WARN")
        _send_json(handler, {"success": False, "error": "客户不存在"}, 404)
        
    except Exception as e:
        log(f"更新客户失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_get_agents(handler):
    """获取业务员列表及客户数量统计"""
    try:
        # 从所有文件中收集业务员信息
        agents = {}
        
        for filepath in [PENDING_FILE, APPROVED_FILE, SENT_FILE]:
            data = _load_json(filepath, [])
            for record in data:
                agent_id = record.get('agent_id') or record.get('sales_id') or '未分配'
                if agent_id not in agents:
                    agents[agent_id] = {
                        'id': agent_id,
                        'name': agent_id,
                        'count': 0
                    }
                agents[agent_id]['count'] += 1
        
        # 转换为列表并排序
        agent_list = sorted(agents.values(), key=lambda x: x['count'], reverse=True)
        
        _send_json(handler, {
            "success": True,
            "data": agent_list
        })
        
    except Exception as e:
        log(f"获取业务员列表失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


def _handle_push_profiles_to_cloud(handler):
    """推送本地客户画像到云端审批系统"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)

        # 获取参数
        customer_id = params.get('customer_id')  # 可选：指定推送某个客户
        filter_complete = params.get('filter_complete', True)  # 是否只推送完整数据

        # 导入 core.customer_sync 模块
        try:
            from core.customer_sync import (
                push_all_profiles_to_cloud,
                push_profile_by_customer_id,
                CLOUD_APPROVAL_SERVER
            )
        except ImportError as e:
            log(f"导入 customer_sync 失败: {e}", "ERROR")
            _send_json(handler, {"success": False, "error": f"模块导入失败: {e}"}, 500)
            return

        # 根据参数决定推送方式
        if customer_id:
            # 推送指定客户
            log(f"推送指定客户 {customer_id} 到云端...", "CLOUD推送")
            result = push_profile_by_customer_id(customer_id, CLOUD_APPROVAL_SERVER)
        else:
            # 批量推送所有客户
            log(f"批量推送本地客户画像到云端...", "CLOUD推送")
            result = push_all_profiles_to_cloud(CLOUD_APPROVAL_SERVER, filter_complete)

        _send_json(handler, result)

    except Exception as e:
        log(f"推送客户画像到云端失败: {e}", "ERROR")
        _send_json(handler, {"success": False, "error": str(e)}, 500)


# 客户ID缓存，用于快速检查
customer_id_cache = {
    "pending": set(),
    "approved": set(),
    "sent": set(),
    "last_update": 0
}

def _update_customer_id_cache():
    """更新客户ID缓存"""
    global customer_id_cache
    
    # 每5秒更新一次缓存
    current_time = time.time()
    if current_time - customer_id_cache["last_update"] < 5:
        return
    
    pending = _load_json(PENDING_FILE, [])
    approved = _load_json(APPROVED_FILE, [])
    sent = _load_json(SENT_FILE, [])
    
    customer_id_cache["pending"] = {r.get("customer_id") for r in pending if r.get("customer_id")}
    customer_id_cache["approved"] = {r.get("customer_id") for r in approved if r.get("customer_id")}
    customer_id_cache["sent"] = {r.get("customer_id") for r in sent if r.get("customer_id")}
    customer_id_cache["last_update"] = current_time
    
    log(f"更新客户ID缓存: pending={len(customer_id_cache['pending'])}, approved={len(customer_id_cache['approved'])}, sent={len(customer_id_cache['sent'])}", "CACHE")


def _handle_check_customer_exists(handler):
    """检查客户是否已存在于云端审批系统"""
    try:
        # 读取请求体
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        params = json.loads(body)

        customer_id = params.get('customer_id', '')

        if not customer_id:
            _send_json(handler, {"success": False, "error": "缺少 customer_id 参数"}, 400)
            return

        # 更新缓存
        _update_customer_id_cache()

        # 检查缓存
        exists = False
        source = ""
        
        if customer_id in customer_id_cache["pending"]:
            exists = True
            source = "pending"
        elif customer_id in customer_id_cache["approved"]:
            exists = True
            source = "approved"
        elif customer_id in customer_id_cache["sent"]:
            exists = True
            source = "sent"

        log(f"客户 {customer_id} 云端存在: {exists}, 来源: {source}", "CHECK")

        _send_json(handler, {
            "success": True,
            "data": {
                "exists": exists,
                "customer_id": customer_id,
                "source": source
            }
        })

    except Exception as e:
        log(f"检查客户存在状态失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        _send_json(handler, {"success": False, "error": str(e)}, 500)
