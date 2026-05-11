"""
合同检测 + 自动生成
从 wechat_monitor.py 拆分，负责合同需求检测、信息提取、合同生成、审批推送。
"""
import os
import re
import json
import time
import traceback
import threading
import requests
from dataclasses import asdict

from monitor_config import (
    _log, _BASE_DIR, CLOUD_SERVER, CLOUD_TOKEN, SALES_ID, API_PORT,
    CONTRACT_AVAILABLE,
    _contract_sse_clients,
)
import monitor_config  # 通过模块访问可变全局变量
from context_manager import get_history


# ========== 合同审批 SSE 通知 ==========

def _notify_contract_change():
    """通知所有 SSE 客户端合同状态变化"""
    dead = []
    for client in _contract_sse_clients:
        try:
            client.write(b"data: update\n\n")
            client.flush()
        except Exception:
            dead.append(client)
    for c in dead:
        _contract_sse_clients.discard(c)


# ========== 合同检测 ==========

def _check_and_generate_contract(msg, message_content: str) -> None:
    """
    后台检测合同需求，信息齐全则静默生成合同。
    信息不够时，把缺失项存入 monitor_config._contract_missing_info，
    由 LLM 生成回复时自动注入提示，让 LLM 自然追问。
    """
    if not CONTRACT_AVAILABLE:
        _log("[合同] 合同模块未加载，跳过")
        return

    if msg.is_group:
        return

    session_id = msg.session_id
    _log(f"[合同] 检查消息: '{message_content[:30]}...' (session={session_id[:15]}...)")
    chat_history = get_history(session_id)

    # ── 阶段1: 等待客户补充信息的会话 ──
    if session_id in monitor_config._pending_info_sessions:
        _log("[合同] 阶段1: 等待补充信息的会话")
        try:
            from contract_generator import extract_order_from_chat, check_missing_info
            pending_order = monitor_config._pending_info_sessions[session_id]
            # 重新提取全部信息（用最新聊天记录，补充信息可能已在历史中）
            updated_order = extract_order_from_chat(
                chat_history, {"wxid": session_id, "nickname": msg.source_name or "客户"}
            )

            # 合并：旧 order 有值保留，新 order 有值覆盖（以新为准）
            for field in ["products", "customer_address", "customer_name",
                           "customer_contact", "customer_phone", "shipping_country",
                           "payment_terms", "voltage", "plug_type", "notes"]:
                new_val = getattr(updated_order, field, None)
                old_val = getattr(pending_order, field, None)
                # 新值非空就用新的，否则保留旧的
                if new_val:
                    setattr(pending_order, field, new_val)
                elif not old_val:
                    # 都为空，保持原样
                    pass

            missing, _ = check_missing_info(pending_order, chat_history, skip_llm=True)
            _log(f"[合同] 阶段1合并后: 产品={pending_order.products}, 客户={pending_order.customer_name}, 电话={pending_order.customer_phone}, 地址={pending_order.customer_address}")
            _log(f"[合同] 阶段1缺失: {missing}")
            if not missing:
                del monitor_config._pending_info_sessions[session_id]
                monitor_config._contract_missing_info.pop(session_id, None)
                _log("[合同] 信息补充完整，生成合同")
                _do_generate_contract_with_order(msg, pending_order)
            else:
                monitor_config._contract_missing_info[session_id] = missing
                _log(f"[合同] 仍缺: {', '.join(missing)}，注入LLM追问")
        except Exception as e:
            _log(f"[合同] 阶段1异常: {e}")
        return

    # ── 阶段2: 客户明确提"合同" → 尝试生成 ──
    if "合同" in message_content:
        _log("[合同] 阶段2: 检测到'合同'关键词，开始提取订单信息...")
        try:
            from contract_generator import extract_order_from_chat, check_missing_info, OrderInfo

            order = None
            cached_order = None
            try:
                from context_manager import get_order_for_contract
                cached_order = get_order_for_contract(session_id)
            except Exception:
                pass

            if cached_order:
                models = cached_order.get("product_info", {}).get("models", [])
                if models:
                    products = [{"name": m, "model": m, "quantity": int(cached_order.get("requirements", {}).get("数量", 1) or 1), "unit_price": 0, "subtotal": 0} for m in models] if models else []
                    order = OrderInfo(
                        products=products,
                        customer_name=cached_order.get("customer_info", {}).get("company", cached_order.get("customer_info", {}).get("name")),  # 优先使用公司名
                        customer_contact=cached_order.get("customer_info", {}).get("name"),  # 联系人
                        customer_phone=cached_order.get("customer_info", {}).get("phone"),
                        customer_address=cached_order.get("customer_info", {}).get("address"),
                        delivery_date=cached_order.get("requirements", {}).get("交货日期"),
                        notes=cached_order.get("requirements", {}).get("备注"),
                    )
                    _log(f"[合同] 从订单跟踪缓存获取: 产品={models}")

            if not order or (not order.products and not any([order.customer_address, order.customer_name, order.customer_phone])):
                customer_info = {"wxid": session_id, "nickname": msg.source_name or "客户"}
                _log("[合同] 调用 extract_order_from_chat...")
                order = extract_order_from_chat(chat_history, customer_info)
                _log(f"[合同] 提取结果: 产品={order.products}, 客户={order.customer_name}, 电话={order.customer_phone}")

            _log("[合同] 调用 check_missing_info...")
            missing, order = check_missing_info(order, chat_history, skip_llm=True)
            _log(f"[合同] 缺失字段: {missing}")
            if not missing:
                monitor_config._contract_missing_info.pop(session_id, None)
                monitor_config._pending_info_sessions.pop(session_id, None)
                _log("[合同] 关键词触发，信息完整，生成合同")
                _do_generate_contract_with_order(msg, order)
            else:
                monitor_config._pending_info_sessions[session_id] = order
                monitor_config._contract_missing_info[session_id] = missing
                _log(f"[合同] 关键词触发，但缺: {', '.join(missing)}，注入LLM追问")
        except Exception as e:
            _log(f"[合同] 阶段2异常: {e}")
            _log(f"[合同] 堆栈: {traceback.format_exc()}")
        return

    # ── 阶段3: 客户确认回复 ──
    # 只有在等待客户补充信息的会话中才处理确认
    if session_id in monitor_config._pending_info_sessions:
        from contract_generator import extract_order_from_chat, check_missing_info
        customer_info = {"wxid": session_id, "nickname": msg.source_name or "客户"}
        order = extract_order_from_chat(chat_history, customer_info)
        missing, order = check_missing_info(order, chat_history, skip_llm=True)
        if not missing:
            monitor_config._contract_missing_info.pop(session_id, None)
            monitor_config._pending_info_sessions.pop(session_id, None)
            _log("[合同] 确认触发，信息完整，生成合同")
            _do_generate_contract_with_order(msg, order)
        else:
            monitor_config._pending_info_sessions[session_id] = order
            monitor_config._contract_missing_info[session_id] = missing
            _log(f"[合同] 确认触发，但缺: {', '.join(missing)}，注入LLM追问")
        return

    # ── 阶段4: 隐含成交信号 → 提取信息，缺信息则注入追问 ──
    from contract_generator import detect_closing_signal, extract_order_from_chat, check_missing_info
    signal = detect_closing_signal(message_content, chat_history)
    if signal is True:
        _log("[合同] 检测到潜在成交信号，尝试提取订单信息...")
        try:
            customer_info = {"wxid": session_id, "nickname": msg.source_name or "客户"}
            order = extract_order_from_chat(chat_history, customer_info)
            missing, order = check_missing_info(order, chat_history, skip_llm=True)
            _log(f"[合同] 提取结果: 产品={order.products}, 客户={order.customer_name}, 电话={order.customer_phone}, 缺失={missing}")
            
            if not missing:
                # 信息完整，直接生成合同
                monitor_config._contract_missing_info.pop(session_id, None)
                monitor_config._pending_info_sessions.pop(session_id, None)
                _log("[合同] 成交信号+信息完整，生成合同")
                _do_generate_contract_with_order(msg, order)
            elif order.products:
                # 有产品但缺客户信息，注入LLM追问（不直接生成）
                monitor_config._pending_info_sessions[session_id] = order
                monitor_config._contract_missing_info[session_id] = missing
                _log(f"[合同] 成交信号但缺: {', '.join(missing)}，注入LLM追问")
            else:
                _log("[合同] 成交信号但无产品信息，跳过生成")
        except Exception as e:
            _log(f"[合同] 阶段4异常: {e}")
            _log(f"[合同] 堆栈: {traceback.format_exc()}")


def _do_generate_contract(msg) -> None:
    """执行合同生成（由强成交信号触发）"""
    try:
        # 优先从订单跟踪系统获取信息（已提取的数据）
        from context_manager import get_order_for_contract
        cached_order = get_order_for_contract(msg.session_id)
        
        order = None
        if cached_order:
            # 复用订单跟踪系统中已提取的信息
            from contract_generator import OrderInfo
            models = cached_order.get("product_info", {}).get("models", [])
            # 转换产品信息为OrderInfo需要的格式
            products = [{"name": m, "model": m, "quantity": int(cached_order.get("requirements", {}).get("数量", 1) or 1), "unit_price": 0, "subtotal": 0} for m in models] if models else []
            order = OrderInfo(
                products=products,
                customer_name=cached_order.get("customer_info", {}).get("company", cached_order.get("customer_info", {}).get("name")),  # 优先使用公司名
                customer_contact=cached_order.get("customer_info", {}).get("name"),  # 联系人
                customer_phone=cached_order.get("customer_info", {}).get("phone"),
                customer_address=cached_order.get("customer_info", {}).get("address"),
                delivery_date=cached_order.get("requirements", {}).get("交货日期"),
                notes=cached_order.get("requirements", {}).get("备注"),
            )
            _log(f"[合同] 复用订单跟踪数据: {models}")
        
        # 如果订单跟踪系统没有数据，才从聊天历史提取
        if not order or (not order.products and not any([order.customer_address, order.customer_name, order.customer_phone])):
            chat_history = get_history(msg.session_id)
            customer_info = {
                "wxid": msg.source_name or msg.session_id,
                "nickname": msg.source_name or ""
            }
            from contract_generator import extract_order_from_chat
            order = extract_order_from_chat(chat_history, customer_info)
            _log(f"[合同] 从聊天历史提取订单信息")
        
        _do_generate_contract_with_order(msg, order)
    except Exception as e:
        _log(f"[合同] 生成失败: {e}")


def _do_generate_contract_with_order(msg, order) -> None:
    """使用提供的订单信息生成合同（后台静默，审批后由人工发送）"""
    try:
        from contract_generator import (
            generate_contract, get_pending_contracts, send_contract,
            approve_contract, reject_contract,
        )
        session_id = msg.session_id
        
        # 检查是否有产品信息（没有产品信息不生成合同）
        if not order.products and not any([
            order.customer_address,
            order.customer_name,
            order.customer_phone
        ]):
            _log("[合同] 检测到成交信号，但信息不足，跳过")
            return

        # 生成合同（状态=PENDING，待审批）
        _log(f"[合同] 生成合同参数: session_id={msg.session_id}, source_name={msg.source_name}")
        contract = generate_contract(
            order=order,
            session_id=msg.session_id,
            customer_wxid=msg.session_id,
            customer_nickname=msg.source_name or "客户"
        )

        _log(f"[合同] 已生成合同 {contract.id}，待审批")
        _log(f"[合同] 合同数据: session_id={contract.session_id}, customer_wxid={contract.customer_wxid}, customer_nickname={contract.customer_nickname}")
        _notify_contract_change()
        pending_count = len(get_pending_contracts())
        _log(f"[合同] 当前待审批: {pending_count}份")
        _log(f"[合同] PDF: {contract.pdf_path}")
        _log(f"[合同] XLSX: {contract.xlsx_path}")

        # 推送合同到云端服务器
        _push_contract_to_cloud(contract)

        # 清除会话状态（合同已生成，不再追问客户信息）
        monitor_config._pending_info_sessions.pop(session_id, None)
        monitor_config._contract_missing_info.pop(session_id, None)
        monitor_config._contract_done_sessions[session_id] = 3  # 标记合同已生成，3轮内防止LLM继续追问
        _log(f"[合同] 已清除会话状态")

        # 通知审批人：只发文字通知（PDF在审批页面预览）
        try:
            from wechat_sender import send_text
            products_info = "、".join([f"{p.get('model','')}×{p.get('quantity',1)}" for p in (order.products or [])])
            
            # 计算总金额，处理字符串类型的 subtotal
            total = 0
            for p in (order.products or []):
                subtotal = p.get("subtotal", 0)
                try:
                    total += float(subtotal) if isinstance(subtotal, str) else subtotal
                except (ValueError, TypeError):
                    pass
            
            from monitor_config import API_TOKEN
            
            # 确保 API_PORT 是字符串
            api_port_str = str(API_PORT)
            
            # 新格式 - 详细版
            notice = f"""📋 新合同待审批
━━━━━━━━━━━━━━━━━━━━
合同号: {contract.id}
客户: {contract.customer_nickname or order.customer_name or '未知'}
产品: {products_info}
金额: ¥{total:,.0f}
地址: {order.customer_address or '待确认'}
━━━━━━━━━━━━━━━━━━━━
[点击审批] {CLOUD_SERVER or ('http://' + os.environ.get('API_HOST', '192.168.0.145') + ':' + api_port_str)}/contracts?id={contract.id}"""

            approval_contact = os.environ.get("APPROVAL_CONTACT", "")  # 从.env读取
            try:
                send_text(approval_contact, notice)
                _log("[合同] 已发送审批通知")
            except Exception as e:
                _log(f"[合同] 发送审批通知失败: {e}")
        except Exception as notify_err:
            _log(f"[合同] 审批通知发送失败: {notify_err}")
            import traceback
            _log(f"[合同] 堆栈: {traceback.format_exc()}")

    except Exception as e:
        _log(f"[合同] 生成失败: {e}")


def _push_contract_to_cloud(contract) -> None:
    """推送合同数据到云端审批服务器"""
    if not CLOUD_SERVER:
        return  # 未配置云端服务器，跳过
    try:
        from contract_generator import load_contracts
        order_dict = asdict(contract.order) if hasattr(contract.order, '__dataclass_fields__') else contract.order
        payload = {
            **order_dict,
            "session_id": contract.session_id,
            "customer_wxid": contract.customer_wxid,
            "customer_nickname": contract.customer_nickname,
            "agent_id": SALES_ID,
        }
        headers = {"Content-Type": "application/json"}
        if CLOUD_TOKEN:
            headers["Authorization"] = f"Bearer {CLOUD_TOKEN}"
        resp = requests.post(
            f"{CLOUD_SERVER.rstrip('/')}/api/contracts/sync",
            json=payload, headers=headers, timeout=30,
            proxies={"http": None, "https": None}
        )
        if resp.status_code == 200:
            data = resp.json()
            _log(f"[合同] 已推送到云端: {data.get('contract_id', contract.id)}")
        else:
            _log(f"[合同] 推送云端失败: HTTP {resp.status_code}")
    except Exception as e:
        _log(f"[合同] 推送云端异常: {e}")


# ========== 合同缺失信息注入（LLM上下文） ==========

def get_contract_missing_info(session_id: str) -> list[str]:
    """获取指定会话的合同缺失字段"""
    return monitor_config._contract_missing_info.get(session_id, [])


def is_contract_done(session_id: str) -> bool:
    """检查合同是否已完成（防止LLM继续追问）"""
    remaining = monitor_config._contract_done_sessions.get(session_id, 0)
    if remaining > 0:
        monitor_config._contract_done_sessions[session_id] = remaining - 1
        if remaining <= 1:
            monitor_config._contract_done_sessions.pop(session_id, None)
        return True
    return False


def clear_contract_session(session_id: str):
    """清除会话的合同状态"""
    monitor_config._contract_missing_info.pop(session_id, None)
    monitor_config._pending_info_sessions.pop(session_id, None)
    monitor_config._contract_done_sessions.pop(session_id, None)
