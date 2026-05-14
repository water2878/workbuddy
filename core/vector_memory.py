"""
本地向量记忆系统
使用 BGE-M3 模型 + LanceDB
适合微信聊天记录等文本记忆的存储和语义检索

注意：导入顺序很重要！必须先导入 lancedb，再导入 sentence_transformers，
否则会导致 Windows 访问冲突错误 (0xC0000005)
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
import os
os.environ['HF_ENDPOINT'] = os.environ.get('HF_ENDPOINT', 'https://hf-mirror.com')


class VectorMemory:
    """本地向量记忆系统 - 畅腾升降桌客服版"""
    
    def __init__(self, db_path: str = None, model_name: str = "BAAI/bge-m3"):
        """
        初始化向量记忆系统
        
        Args:
            db_path: 向量数据库存储路径，默认在 Claw 项目 data/vector_db
            model_name: 嵌入模型名称，默认BGE-M3（中文优化）
        """
        # 默认路径：Claw项目 data/vector_db
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "vector_db")
        """
        初始化向量记忆系统
        
        Args:
            db_path: 向量数据库存储路径
            model_name: 嵌入模型名称，默认BGE-M3（中文优化）
        """
        self.db_path = db_path
        self.model_name = model_name
        
        # 初始化嵌入模型（首次会自动下载，约2GB）
        print(f"[初始化] 加载嵌入模型: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"[初始化] 模型维度: {self.embedding_dim}")
        
        # 初始化LanceDB
        os.makedirs(db_path, exist_ok=True)
        self.db = lancedb.connect(db_path)
        print(f"[初始化] 数据库路径: {db_path}")
        
        # 获取或创建表
        self.table_name = "chat_memories"
        self._init_table()
    
    def _init_table(self):
        """初始化或连接记忆表"""
        try:
            self.table = self.db.open_table(self.table_name)
            print(f"[初始化] 已连接表: {self.table_name}")
        except Exception:
            # 表不存在，创建新表
            print(f"[初始化] 创建新表: {self.table_name}")
            # LanceDB需要先有数据才能创建表
            sample_data = [{
                "id": "sample",
                "text": "示例记忆",
                "vector": [0.0] * self.embedding_dim,
                "source": "system",
                "people": json.dumps([]),
                "type": "sample",
                "created_at": datetime.now().isoformat()
            }]
            self.table = self.db.create_table(self.table_name, data=sample_data)
            # 删除示例数据
            self.table.delete('id = "sample"')
    
    def _generate_id(self, text: str) -> str:
        """为文本生成唯一ID"""
        return hashlib.md5(text.encode()).hexdigest()[:16]
    
    def _extract_people(self, text: str) -> List[str]:
        """从文本中提取客户名称（简单实现）"""
        # 客服场景：提取客户公司名或联系人
        common_customers = ["健康办公研究社", "李生", "畅腾", "客户"]
        found = [name for name in common_customers if name in text]
        return found
    
    def store(self, text: str, source: str = "unknown", 
              memory_type: str = "chat", customer: str = "", 
              metadata: Optional[Dict] = None) -> str:
        """
        存储记忆
        
        Args:
            text: 记忆文本内容
            source: 来源（如"微信-健康办公研究社"）
            memory_type: 记忆类型（chat/product/price/order等）
            customer: 客户名称
            metadata: 额外元数据
        
        Returns:
            记忆ID
        """
        # 生成向量
        vector = self.model.encode(text, normalize_embeddings=True).tolist()
        
        # 生成ID
        memory_id = self._generate_id(text + datetime.now().isoformat())
        
        # 提取客户名
        people = self._extract_people(text)
        if customer and customer not in people:
            people.append(customer)
        
        # 构建数据
        data = {
            "id": memory_id,
            "text": text,
            "vector": vector,
            "source": source,
            "customer": customer or "",
            "people": json.dumps(people, ensure_ascii=False),
            "type": memory_type,
            "created_at": datetime.now().isoformat()
        }
        
        # 存入数据库
        self.table.add([data])
        print(f"[存储] ID={memory_id}, 来源={source}, 类型={memory_type}")
        
        return memory_id
    
    def search(self, query: str, top_k: int = 5, 
               filter_source: Optional[str] = None,
               filter_customer: Optional[str] = None) -> List[Dict]:
        """
        语义搜索记忆
        
        Args:
            query: 查询文本
            top_k: 返回最相关的k条
            filter_source: 按来源过滤（如"微信"）
            filter_customer: 按客户过滤（如"健康办公研究社"）
        
        Returns:
            相关记忆列表
        """
        # 查询向量化
        query_vector = self.model.encode(query, normalize_embeddings=True).tolist()
        
        # 构建搜索
        search = self.table.search(query_vector)
        
        # 应用过滤
        filters = []
        if filter_source:
            filters.append(f'source = "{filter_source}"')
        if filter_customer:
            filters.append(f'customer = "{filter_customer}"')
        
        if filters:
            search = search.where(' AND '.join(filters))
        
        # 执行搜索
        results = search.limit(top_k).to_pandas()
        
        # 格式化结果
        memories = []
        for _, row in results.iterrows():
            memories.append({
                "id": row["id"],
                "text": row["text"],
                "source": row["source"],
                "customer": row.get("customer", ""),
                "people": json.loads(row["people"]),
                "type": row["type"],
                "created_at": row["created_at"],
                "score": row.get("_distance", 0)  # 相似度分数
            })
        
        return memories
    
    def list_all(self, limit: int = 100) -> List[Dict]:
        """列出所有记忆"""
        results = self.table.to_pandas().head(limit)
        
        memories = []
        for _, row in results.iterrows():
            memories.append({
                "id": row["id"],
                "text": row["text"][:50] + "..." if len(row["text"]) > 50 else row["text"],
                "source": row["source"],
                "type": row["type"],
                "created_at": row["created_at"]
            })
        
        return memories
    
    def delete(self, memory_id: str) -> bool:
        """删除指定记忆"""
        try:
            self.table.delete(f'id = "{memory_id}"')
            print(f"[删除] ID={memory_id}")
            return True
        except Exception as e:
            print(f"[删除失败] {e}")
            return False
    
    def stats(self) -> Dict:
        """获取统计信息"""
        count = len(self.table.to_pandas())
        return {
            "total_memories": count,
            "db_path": self.db_path,
            "model": self.model_name,
            "embedding_dim": self.embedding_dim
        }


# 便捷函数
def init_memory(db_path: str = "./chat_memory") -> VectorMemory:
    """初始化记忆系统"""
    return VectorMemory(db_path=db_path)


if __name__ == "__main__":
    # 测试 - 畅腾升降桌客服场景
    print("=" * 50)
    print("畅腾升降桌客服向量记忆系统测试")
    print("=" * 50)
    
    # 初始化
    memory = init_memory()
    
    # 存储测试数据 - 客服场景
    test_memories = [
        ("客户咨询T621升降桌，需要10套，白色", "微信-健康办公研究社", "询价", "健康办公研究社"),
        ("F4404椭圆管不锈钢款，双电机，承重120kg", "微信-健康办公研究社", "产品介绍", "健康办公研究社"),
        ("客户说之前买过T728手摇款，现在想换电动的", "微信-老客户", "需求", "老客户"),
        ("T621单电机款，价格1280一套，含税加3%", "微信-健康办公研究社", "报价", "健康办公研究社"),
        ("客户要求看F4404实物图", "微信-健康办公研究社", "需求", "健康办公研究社"),
    ]
    
    print("\n[测试] 存储客服记忆...")
    for text, source, mtype, customer in test_memories:
        memory.store(text, source=source, memory_type=mtype, customer=customer)
    
    # 搜索测试
    print("\n[测试] 语义搜索...")
    queries = [
        "客户想要什么型号",
        "T621多少钱",
        "不锈钢款有哪些",
    ]
    
    for query in queries:
        print(f"\n查询: '{query}'")
        results = memory.search(query, top_k=2)
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['customer']}] {r['text'][:40]}... (score: {r['score']:.3f})")
    
    # 按客户过滤搜索
    print("\n[测试] 按客户过滤搜索...")
    results = memory.search("价格", filter_customer="健康办公研究社", top_k=3)
    print(f"健康办公研究社的价格相关记忆:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['text'][:50]}...")
    
    # 统计
    print("\n[统计]")
    print(memory.stats())
