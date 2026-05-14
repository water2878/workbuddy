"""
WorkBuddy Code 记忆桥接模块
自动存储对话历史，提供记忆上下文
"""

import os
import sys

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from vector_memory_wb import (
        get_memory,
        store_user_message,
        store_assistant_message,
        search_memories,
        get_memory_context
    )
    MEMORY_ENABLED = True
except ImportError as e:
    print(f"[记忆系统] 加载失败: {e}")
    MEMORY_ENABLED = False


def remember(text: str, source: str = "user", session: str = "") -> str:
    """
    存储记忆

    Args:
        text: 记忆内容
        source: "user" 或 "assistant"
        session: 会话标识

    Returns:
        记忆ID
    """
    if not MEMORY_ENABLED:
        return ""

    try:
        if source == "user":
            return store_user_message(text, session)
        else:
            return store_assistant_message(text, session)
    except Exception as e:
        print(f"[记忆存储失败] {e}")
        return ""


def recall(query: str = None, top_k: int = 3) -> str:
    """
    回忆相关记忆

    Args:
        query: 查询内容，None则返回最近记忆
        top_k: 返回条数

    Returns:
        格式化的记忆文本
    """
    if not MEMORY_ENABLED:
        return ""

    try:
        return get_memory_context(query, top_k)
    except Exception as e:
        print(f"[记忆检索失败] {e}")
        return ""


def stats():
    """获取记忆统计"""
    if not MEMORY_ENABLED:
        return {"status": "disabled"}

    try:
        memory = get_memory()
        return memory.stats()
    except Exception as e:
        return {"status": "error", "error": str(e)}


# 便捷函数
def store_task(description: str, result: str = ""):
    """存储任务记录"""
    if not MEMORY_ENABLED:
        return ""

    try:
        memory = get_memory()
        text = f"任务: {description}"
        if result:
            text += f" | 结果: {result}"
        return memory.store(text, source="assistant", memory_type="task")
    except Exception as e:
        print(f"[任务存储失败] {e}")
        return ""


def store_decision(context: str, decision: str, reason: str = ""):
    """存储决策记录"""
    if not MEMORY_ENABLED:
        return ""

    try:
        memory = get_memory()
        text = f"决策: {decision} | 背景: {context}"
        if reason:
            text += f" | 原因: {reason}"
        return memory.store(text, source="assistant", memory_type="decision")
    except Exception as e:
        print(f"[决策存储失败] {e}")
        return ""


def store_error(error_msg: str, context: str = ""):
    """存储错误记录"""
    if not MEMORY_ENABLED:
        return ""

    try:
        memory = get_memory()
        text = f"错误: {error_msg}"
        if context:
            text += f" | 上下文: {context}"
        return memory.store(text, source="system", memory_type="error")
    except Exception as e:
        print(f"[错误存储失败] {e}")
        return ""


if __name__ == "__main__":
    print("=" * 50)
    print("WorkBuddy Code 记忆桥接测试")
    print("=" * 50)

    # 存储测试
    print("\n[存储] 用户消息...")
    remember("帮我配置向量记忆系统", "user")

    print("\n[存储] 助手回复...")
    remember("好的，我来配置向量记忆系统", "assistant")

    print("\n[存储] 任务记录...")
    store_task("创建vector_memory_wb.py", "成功创建")

    # 检索测试
    print("\n[检索] 相关记忆...")
    context = recall("向量记忆")
    print(f"结果:\n{context}")

    # 统计
    print("\n[统计]")
    print(stats())
