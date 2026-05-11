"""
订单状态跟踪系统
记录订单从咨询到成交的完整流程
"""
import os
import json
import time
from datetime import datetime

try:
    from core.config import log as _log, BASE_DIR as _BASE_DIR
except ImportError:
    try:
        from config import log as _log, BASE_DIR as _BASE_DIR
    except ImportError:
        from datetime import datetime as _dt
        def _log(text: str, tag: str = "INFO"):
            print(f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] [{tag}] {text}", flush=True)
        _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 订单状态定义
ORDER_STATUS = {
    "initial_inquiry": "初始咨询",
    "product_selection": "产品选择",
    "requirement_confirmation": "需求确认",
    "contract_preparation": "合同准备",
    "approval_pending": "审批中",
    "closed_won": "已成交",
    "closed_lost": "已拒绝"
}

# 订单状态文件目录
ORDER_DIR = os.path.join(_BASE_DIR, "data", "orders")
os.makedirs(ORDER_DIR, exist_ok=True)

class OrderTracker:
    """订单状态跟踪器"""
    
    def __init__(self):
        self.orders = {}
        self._load_orders()
    
    def _load_orders(self):
        """加载所有订单"""
        for fname in os.listdir(ORDER_DIR):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(ORDER_DIR, fname), "r", encoding="utf-8") as f:
                        order = json.load(f)
                    session_id = order.get("session_id")
                    if session_id:
                        self.orders[session_id] = order
                except Exception as e:
                    _log(f"[订单跟踪] 加载订单失败 {fname}: {e}")
    
    def _save_order(self, order):
        """保存订单"""
        session_id = order.get("session_id")
        if session_id:
            safe_id = session_id.replace("@chatroom", "_group").replace(os.sep, "_")
            filepath = os.path.join(ORDER_DIR, f"order_{safe_id}.json")
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(order, f, ensure_ascii=False, indent=2)
                _log(f"[订单跟踪] 已保存订单 {session_id[:20]}...")
            except Exception as e:
                _log(f"[订单跟踪] 保存订单失败: {e}")
    
    def get_order(self, session_id):
        """获取会话的订单信息"""
        return self.orders.get(session_id)
    
    def create_order(self, session_id, initial_message):
        """创建新订单"""
        order = {
            "order_id": f"ORD_{int(time.time())}_{session_id[:8]}",
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "status": "initial_inquiry",
            "status_history": [{
                "status": "initial_inquiry",
                "timestamp": datetime.now().isoformat(),
                "message": "初始咨询"
            }],
            "customer_info": {},
            "product_info": {},
            "requirements": {},
            "contract_info": {},
            "notes": [initial_message]
        }
        self.orders[session_id] = order
        self._save_order(order)
        return order
    
    # 状态等级（只升不降）
    _STATUS_LEVEL = {"initial_inquiry": 0, "product_selection": 1, "requirement_confirmation": 2,
                     "contract_preparation": 3, "approval_pending": 4}

    def update_status(self, session_id, status, message=""):
        """更新订单状态（只升不降）"""
        order = self.orders.get(session_id)
        if not order:
            order = self.create_order(session_id, message)
        
        # 只允许状态升级，不允许降级
        current_level = self._STATUS_LEVEL.get(order["status"], 0)
        new_level = self._STATUS_LEVEL.get(status, 0)
        if new_level <= current_level:
            return order
        
        if order["status"] != status:
            order["status"] = status
            order["status_history"].append({
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "message": message
            })
            self._save_order(order)
            _log(f"[订单跟踪] 订单状态更新: {session_id[:20]}... -> {ORDER_STATUS.get(status, status)}")
        
        return order
    
    def update_product_info(self, session_id, product_info):
        """更新产品信息"""
        order = self.orders.get(session_id)
        if not order:
            order = self.create_order(session_id, "产品信息更新")
        
        # 新结构 products[] 更新时，清理旧结构字段，避免数据冗余
        if product_info.get("products"):
            order["product_info"].pop("models", None)
            order["product_info"].pop("quantity", None)
            order["product_info"].pop("color", None)
        
        order["product_info"].update(product_info)
        self._save_order(order)
        return order
    
    def update_requirements(self, session_id, requirements):
        """更新需求信息"""
        order = self.orders.get(session_id)
        if not order:
            order = self.create_order(session_id, "需求信息更新")
        
        order["requirements"].update(requirements)
        self._save_order(order)
        return order
    
    def update_customer_info(self, session_id, customer_info):
        """更新客户信息"""
        order = self.orders.get(session_id)
        if not order:
            order = self.create_order(session_id, "客户信息更新")
        
        order["customer_info"].update(customer_info)
        self._save_order(order)
        return order
    
    def update_contract_info(self, session_id, contract_info):
        """更新合同信息"""
        order = self.orders.get(session_id)
        if not order:
            order = self.create_order(session_id, "合同信息更新")
        
        order["contract_info"].update(contract_info)
        self._save_order(order)
        return order
    
    def add_note(self, session_id, note):
        """添加备注"""
        order = self.orders.get(session_id)
        if not order:
            order = self.create_order(session_id, note)
        else:
            order["notes"].append(note)
            self._save_order(order)
        return order
    
    def get_order_status(self, session_id):
        """获取订单状态"""
        order = self.orders.get(session_id)
        if order:
            return order["status"]
        return None
    
    def get_order_for_contract(self, session_id):
        """获取合同生成所需的订单信息（供合同系统复用）"""
        order = self.orders.get(session_id)
        if not order:
            return None
        
        return {
            "session_id": session_id,
            "product_info": order.get("product_info", {}),
            "customer_info": order.get("customer_info", {}),
            "requirements": order.get("requirements", {}),
            "contract_info": order.get("contract_info", {}),
            "notes": order.get("notes", []),
            "order_id": order.get("order_id"),
        }
    
    def get_order_context(self, session_id):
        """获取订单上下文信息"""
        order = self.orders.get(session_id)
        if not order:
            return ""
        
        context_parts = []
        context_parts.append(f"订单状态: {ORDER_STATUS.get(order['status'], order['status'])}")
        
        if order.get("product_info"):
            pi = order["product_info"]
            # 新结构：products 列表（每个产品独立）
            if pi.get("products") and isinstance(pi["products"], list):
                prod_lines = []
                for i, p in enumerate(pi["products"], 1):
                    if isinstance(p, dict):
                        parts = [f"型号{p.get('model', '?')}"]
                        if p.get("quantity"):
                            parts.append(f"{p['quantity']}台")
                        if p.get("color"):
                            parts.append(p["color"])
                        if p.get("desk_size"):
                            parts.append(f"尺寸{p['desk_size']}")
                        if p.get("weight"):
                            parts.append(p["weight"])
                        if p.get("volume"):
                            parts.append(p["volume"])
                        if p.get("unit_price"):
                            parts.append(f"¥{p['unit_price']}")
                        prod_lines.append(f"  {i}. {' '.join(parts)}")
                if prod_lines:
                    context_parts.append("产品信息:\n" + "\n".join(prod_lines))
            # 旧结构：扁平 models + quantity + color
            elif pi.get("models"):
                models_str = ", ".join(pi["models"])
                qty_str = f", {pi['quantity']}台" if pi.get("quantity") else ""
                color_str = f", {pi['color']}" if pi.get("color") else ""
                context_parts.append(f"产品信息: {models_str}{qty_str}{color_str}")
        
        if order.get("requirements"):
            reqs = []
            for key, value in order["requirements"].items():
                reqs.append(f"{key}: {value}")
            if reqs:
                context_parts.append(f"需求信息: {', '.join(reqs)}")
        
        if order.get("contract_info"):
            contracts = []
            for key, value in order["contract_info"].items():
                contracts.append(f"{key}: {value}")
            if contracts:
                context_parts.append(f"合同信息: {', '.join(contracts)}")
        
        if order.get("status_history"):
            recent_status = order["status_history"][-3:]
            status_changes = []
            for status in reversed(recent_status):
                status_changes.append(f"{status['timestamp'][:10]}: {ORDER_STATUS.get(status['status'], status['status'])}")
            if status_changes:
                context_parts.append(f"最近状态: {', '.join(status_changes)}")
        
        if context_parts:
            return "\n" + "\n".join(context_parts)
        return ""

# 单例实例
order_tracker = OrderTracker()

# 导出函数
def get_order(session_id):
    return order_tracker.get_order(session_id)

def update_order_status(session_id, status, message=""):
    return order_tracker.update_status(session_id, status, message)

def update_product_info(session_id, product_info):
    return order_tracker.update_product_info(session_id, product_info)

def update_requirements(session_id, requirements):
    return order_tracker.update_requirements(session_id, requirements)

def update_customer_info(session_id, customer_info):
    return order_tracker.update_customer_info(session_id, customer_info)

def update_contract_info(session_id, contract_info):
    return order_tracker.update_contract_info(session_id, contract_info)

def get_order_for_contract(session_id):
    return order_tracker.get_order_for_contract(session_id)

def add_order_note(session_id, note):
    return order_tracker.add_note(session_id, note)

def get_order_status(session_id):
    return order_tracker.get_order_status(session_id)

def get_order_context(session_id):
    return order_tracker.get_order_context(session_id)
