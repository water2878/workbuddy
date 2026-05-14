"""
WorkBuddy Code 向量记忆系统
使用 BGE-M3 模型 + LanceDB
存储和检索与用户的对话历史

注意：导入顺序很重要！必须先导入 lancedb，再导入 sentence_transformers
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np

# 向量数据库（必须先导入）
import lancedb

# 向量嵌入模型（必须在 lancedb 之后导入）
from sentence_transformers import SentenceTransformer

# 设置 HuggingFace 镜像（国内加速）
os.environ['HF_ENDPOINT'] = os.environ.get('HF_ENDPOINT', 'https://hf-mirror.com')


class WorkBuddyMemory:
    """WorkBuddy Code 向量记忆系统"""

    def __init__(self, db_path: str = None, model_name: str = "BAAI/bge-m3"):
        """
        初始化向量记忆系统

        Args:
            db_path: 向量数据库存储路径，默认在 .workbuddy/vector_db
            model_name: 嵌入模型名称，默认BGE-M3（中文优化）
        """
        # 默认路径：.workbuddy/vector_db
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "vector_db")

        self.db_path = db_path
        self.model_name = model_name

        # 初始化嵌入模型（首次会自动下载，约2GB）
        print(f"[WorkBuddy记忆] 加载嵌入模型: {model_name}")
        self.model = SentenceTransformer(model_name, cache_folder=os.path.expanduser("~/.cache/huggingface/hub"))
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"[WorkBuddy记忆] 模型维度: {self.embedding_dim}")

        # 初始化LanceDB
        os.makedirs(db_path, exist_ok=True)
        self.db = lancedb.connect(db_path)
        print(f"[WorkBuddy记忆] 数据库路径: {db_path}")

        # 获取或创建表
        self.table_name = "workbuddy_memories"
        self._init_table()

    def _init_table(self):
        """初始化或连接记忆表"""
        try:
            self.table = self.db.open_table(self.table_name)
            print(f"[WorkBuddy记忆] 已连接表: {self.table_name}")
        except Exception:
            # 表不存在，创建新表
            print(f"[WorkBuddy记忆] 创建新表: {self.table_name}")
            sample_data = [{
                "id": "sample",
                "text": "示例记忆",
                "vector": [0.0] * self.embedding_dim,
                "source": "system",
                "session": "",
                "type": "sample",
                "created_at": datetime.now().isoformat()
            }]
            self.table = self.db.create_table(self.table_name, data=sample_data)
            self.table.delete('id = "sample"')

    def _generate_id(self, text: str) -> str:
        """为文本生成唯一ID"""
        return hashlib.md5(text.encode()).hexdigest()[:16]

    def store(self, text: str, source: str = "user",
              memory_type: str = "chat", session: str = "",
              metadata: Optional[Dict] = None) -> str:
        """
        存储记忆

        Args:
            text: 记忆文本内容
            source: 来源（"user"或"assistant"）
            memory_type: 记忆类型（chat/task/decision/error等）
            session: 会话ID
            metadata: 额外元数据

        Returns:
            记忆ID
        """
        # 生成向量
        vector = self.model.encode(text, normalize_embeddings=True).tolist()

        # 生成ID
        memory_id = self._generate_id(text + datetime.now().isoformat())

        # 构建数据
        data = {
            "id": memory_id,
            "text": text,
            "vector": vector,
            "source": source,
            "session": session or "",
            "type": memory_type,
            "created_at": datetime.now().isoformat()
        }

        # 存入数据库
        self.table.add([data])
        print(f"[WorkBuddy记忆] 已存储: {text[:50]}...")

        return memory_id

    def search(self, query: str, top_k: int = 5,
               filter_type: Optional[str] = None) -> List[Dict]:
        """
        语义搜索记忆

        Args:
            query: 查询文本
            top_k: 返回最相关的k条
            filter_type: 按类型过滤

        Returns:
            相关记忆列表
        """
        # 查询向量化
        query_vector = self.model.encode(query, normalize_embeddings=True).tolist()

        # 构建搜索
        search = self.table.search(query_vector)

        # 应用过滤
        if filter_type:
            search = search.where(f'type = "{filter_type}"')

        # 执行搜索
        results = search.limit(top_k).to_pandas()

        # 格式化结果
        memories = []
        for _, row in results.iterrows():
            memories.append({
                "id": row["id"],
                "text": row["text"],
                "source": row["source"],
                "type": row["type"],
                "created_at": row["created_at"],
                "score": row.get("_distance", 0)
            })

        return memories

    def get_recent(self, limit: int = 10) -> List[Dict]:
        """获取最近记忆"""
        results = self.table.to_pandas()
        results = results.sort_values('created_at', ascending=False).head(limit)

        memories = []
        for _, row in results.iterrows():
            memories.append({
                "id": row["id"],
                "text": row["text"][:100] + "..." if len(row["text"]) > 100 else row["text"],
                "source": row["source"],
                "type": row["type"],
                "created_at": row["created_at"]
            })

        return memories

    def stats(self) -> Dict:
        """获取统计信息"""
        count = len(self.table.to_pandas())
        return {
            "total_memories": count,
            "db_path": self.db_path,
            "model": self.model_name,
            "embedding_dim": self.embedding_dim
        }


# 全局单例
_wb_memory = None

def get_memory() -> WorkBuddyMemory:
    """获取WorkBuddy记忆实例（单例）"""
    global _wb_memory
    if _wb_memory is None:
        _wb_memory = WorkBuddyMemory()
    return _wb_memory


def store_user_message(text: str, session: str = "") -> str:
    """存储用户消息"""
    memory = get_memory()
    return memory.store(text, source="user", memory_type="chat", session=session)


def store_assistant_message(text: str, session: str = "") -> str:
    """存储助手回复"""
    memory = get_memory()
    return memory.store(text, source="assistant", memory_type="chat", session=session)


def search_memories(query: str, top_k: int = 5) -> List[Dict]:
    """搜索相关记忆"""
    memory = get_memory()
    return memory.search(query, top_k=top_k)


def get_memory_context(query: str = None, top_k: int = 3) -> str:
    """
    获取记忆上下文，用于生成回复

    Args:
        query: 查询内容，如果为None则返回最近记忆
        top_k: 返回记忆条数

    Returns:
        格式化的记忆文本
    """
    memory = get_memory()

    if query:
        results = memory.search(query, top_k=top_k)
    else:
        results = memory.get_recent(limit=top_k)

    if not results:
        return ""

    context_parts = []
    for r in results:
        source_label = "用户" if r["source"] == "user" else "助手"
        context_parts.append(f"[{source_label}] {r['text']}")

    return "\n".join(context_parts)


if __name__ == "__main__":
    # 测试
    print("=" * 50)
    print("WorkBuddy Code 向量记忆系统测试")
    print("=" * 50)

    # 初始化
    memory = get_memory()

    # 存储测试数据
    test_memories = [
        ("帮我查一下T621的价格", "user", "chat"),
        ("T621双电机3节椭圆管，900元一套", "assistant", "chat"),
        ("客户画像更新失败怎么办", "user", "task"),
        ("检查send_reply.py的写入逻辑", "assistant", "task"),
    ]

    print("\n[测试] 存储记忆...")
    for text, source, mtype in test_memories:
        memory.store(text, source=source, memory_type=mtype)

    # 搜索测试
    print("\n[测试] 语义搜索...")
    queries = [
        "升降桌多少钱",
        "客户画像问题",
    ]

    for query in queries:
        print(f"\n查询: '{query}'")
        results = search_memories(query, top_k=2)
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['source']}] {r['text'][:40]}...")

    # 获取记忆上下文
    print("\n[测试] 获取记忆上下文...")
    context = get_memory_context("T621价格")
    print(f"上下文:\n{context}")

    # 统计
    print("\n[统计]")
    print(memory.stats())
