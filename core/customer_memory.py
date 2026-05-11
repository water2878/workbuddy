"""
客户记忆管理系统
整合向量记忆 + 客户档案 + 对话持久化
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from vector_memory import VectorMemory


class CustomerMemory:
    """客户记忆管理系统"""
    
    def __init__(self, base_dir: str = "./chat_history", vector_db=None):
        """
        初始化客户记忆系统
        
        Args:
            base_dir: 对话历史存储路径
            vector_db: 可选的 VectorMemory 实例（复用已有单例，避免重复加载BGE-M3模型）
        """
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        
        # 初始化向量记忆（复用外部单例或自建）
        if vector_db is not None:
            self.vector_db = vector_db
        else:
            self.vector_db = VectorMemory(
                db_path="./vector_db",
                model_name="BAAI/bge-m3"
            )
        
        # 客户档案目录
        self.contacts_dir = "./.workbuddy/memory/contacts"
        os.makedirs(self.contacts_dir, exist_ok=True)
    
    def store_message(self, session_id: str, role: str, content: str, 
                      source_name: str = "", message_type: str = "text"):
        """
        存储单条消息（持久化 + 向量化）
        
        Args:
            session_id: 会话ID (wxid_xxx)
            role: user/assistant
            content: 消息内容
            source_name: 发送者名称
            message_type: text/image/voice
        """
        timestamp = datetime.now().isoformat()
        
        # 1. 持久化到文件
        self._append_to_file(session_id, {
            "timestamp": timestamp,
            "role": role,
            "content": content,
            "source_name": source_name,
            "type": message_type
        })
        
        # 2. 向量化存储（用于语义搜索）
        if role == "user" and content:
            self.vector_db.store(
                text=f"[{source_name}] {content}",
                source=session_id,
                memory_type="customer_chat",
                metadata={
                    "role": role,
                    "timestamp": timestamp,
                    "session_id": session_id
                }
            )
    
    def _append_to_file(self, session_id: str, message: dict):
        """追加消息到文件"""
        # 按日期分文件
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{session_id}_{date_str}.jsonl"
        filepath = os.path.join(self.base_dir, filename)
        
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")
    
    def get_chat_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        """
        获取最近对话历史
        
        Args:
            session_id: 会话ID
            limit: 返回最近多少条
        
        Returns:
            对话列表
        """
        messages = []
        
        # 读取今天的文件
        date_str = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(self.base_dir, f"{session_id}_{date_str}.jsonl")
        
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        messages.append(json.loads(line))
        
        # 返回最近的
        return messages[-limit:] if len(messages) > limit else messages
    
    def search_customer_memory(self, query: str, session_id: Optional[str] = None, 
                               top_k: int = 5) -> List[Dict]:
        """
        语义搜索客户历史对话
        
        Args:
            query: 查询内容
            session_id: 指定客户（None则搜索所有）
            top_k: 返回数量
        
        Returns:
            相关记忆列表
        """
        if session_id:
            return self.vector_db.search(query, top_k=top_k, filter_source=session_id)
        else:
            return self.vector_db.search(query, top_k=top_k)
    
    def create_customer_profile(self, wxid: str, nickname: str = "", 
                                source: str = "未知") -> str:
        """
        创建客户档案
        
        Args:
            wxid: 微信ID
            nickname: 昵称
            source: 来源
        
        Returns:
            档案路径
        """
        filepath = os.path.join(self.contacts_dir, f"{wxid}.md")
        
        if os.path.exists(filepath):
            return filepath  # 已存在
        
        template = f"""# {nickname or '未命名客户'}

- **wxid**: {wxid}
- **昵称**: {nickname}
- **首次接触**: {datetime.now().strftime("%Y-%m-%d")}
- **来源**: {source}
- **客户类型**: 待分类

## 基本信息
- **称呼**: 待填写
- **地区**: 待填写
- **行业**: 待填写

## 沟通历史
| 时间 | 事件 | 备注 |
|------|------|------|

## 需求偏好
- **产品偏好**: 
- **预算范围**: 
- **用途**: 
- **特殊要求**: 

## 订单记录
- [ ] 暂无订单

## 跟进状态
- **当前状态**: 新客
- **下次跟进**: 
- **备注**: 

---
*创建时间: {datetime.now().isoformat()}*
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(template)
        
        return filepath
    
    def get_customer_profile(self, wxid: str) -> Optional[str]:
        """获取客户档案内容"""
        filepath = os.path.join(self.contacts_dir, f"{wxid}.md")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        return None
    
    def update_customer_profile(self, wxid: str, updates: dict):
        """
        更新客户档案
        
        Args:
            wxid: 客户ID
            updates: 更新内容字典
        """
        filepath = os.path.join(self.contacts_dir, f"{wxid}.md")
        
        if not os.path.exists(filepath):
            self.create_customer_profile(wxid)
        
        # 读取现有内容
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 追加更新记录到沟通历史
        update_line = f"\n| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {updates.get('event', '更新')} | {updates.get('note', '')} |"
        
        # 简单追加（实际可以更智能地解析和更新）
        content += f"\n\n## 更新记录\n{update_line}"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    
    def get_all_customers(self) -> List[Dict]:
        """获取所有客户列表"""
        customers = []
        
        for filename in os.listdir(self.contacts_dir):
            if filename.endswith(".md") and filename != "README.md":
                wxid = filename[:-3]
                profile = self.get_customer_profile(wxid)
                
                # 简单解析昵称
                nickname = "未知"
                if profile:
                    for line in profile.split("\n"):
                        if line.startswith("- **昵称**:"):
                            nickname = line.split(":")[1].strip()
                            break
                
                customers.append({
                    "wxid": wxid,
                    "nickname": nickname
                })
        
        return customers
    
    def stats(self) -> Dict:
        """获取统计信息"""
        return {
            "vector_db": self.vector_db.stats(),
            "customer_count": len([f for f in os.listdir(self.contacts_dir) if f.endswith(".md")]),
            "chat_files": len([f for f in os.listdir(self.base_dir) if f.endswith(".jsonl")])
        }


# 单例模式
_customer_memory = None

def get_customer_memory() -> CustomerMemory:
    """获取客户记忆系统实例（单例）"""
    global _customer_memory
    if _customer_memory is None:
        _customer_memory = CustomerMemory()
    return _customer_memory


if __name__ == "__main__":
    # 测试
    print("=" * 50)
    print("客户记忆系统测试")
    print("=" * 50)
    
    cm = CustomerMemory()
    
    # 测试存储消息
    print("\n[测试] 存储消息...")
    cm.store_message("wxid_test123", "user", "T423多少钱？", "客户A")
    cm.store_message("wxid_test123", "assistant", "1080", "李先生")
    cm.store_message("wxid_test123", "user", "有什么颜色？", "客户A")
    
    # 测试获取历史
    print("\n[测试] 获取对话历史...")
    history = cm.get_chat_history("wxid_test123")
    for h in history:
        print(f"  [{h['role']}] {h['content']}")
    
    # 测试语义搜索
    print("\n[测试] 语义搜索...")
    results = cm.search_customer_memory("价格相关的问题")
    for r in results:
        print(f"  [{r['source']}] {r['text'][:40]}...")
    
    # 测试创建档案
    print("\n[测试] 创建客户档案...")
    profile_path = cm.create_customer_profile("wxid_test123", "客户A", "自然流量")
    print(f"  档案路径: {profile_path}")
    
    # 统计
    print("\n[统计]")
    print(cm.stats())
