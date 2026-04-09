# -*- coding: utf-8 -*-
"""
WorkBuddy 回复生成器
──────────────────────────────────────
用法：由 WorkBuddy 运行此脚本。

通信流程：
  wechat_monitor.py 写 pending.json
        ↓
  本脚本读取 → 构建 prompt → 写入 pending.json[wb_prompt]
        ↓
  WorkBuddy 读取 pending.json[wb_prompt]，生成回复后
  写入 pending.json[wb_reply] 并将 status 改为 "replied"
        ↓
  本脚本检测到 "replied" → 写出 reply.json
        ↓
  wechat_monitor.py 读 reply.json → 发送
"""

import sys
import io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json
import time
from pathlib import Path
from datetime import datetime

# =====================================================================
# 配置
# =====================================================================

COMM_DIR     = Path(__file__).parent / "wb_comm"
PENDING_FILE = COMM_DIR / "pending.json"
REPLY_FILE   = COMM_DIR / "reply.json"

CHECK_INTERVAL = 0.5   # 轮询间隔（秒）
WB_TIMEOUT     = 120   # 等待 WorkBuddy 写入回复的超时（秒）

REPLY_STYLE = (
    "你是用户的微信助手，代替用户回复消息。"
    "要求：语气自然像真人、简洁不啰嗦、中文回复、不要使用 emoji。"
)

# =====================================================================


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def build_prompt(contact: str, messages: list) -> str:
    """把联系人名和消息列表拼成给 WorkBuddy 的 prompt"""
    history = ""
    for m in messages:
        speaker = contact if m["speaker"] == "other" else "我"
        history += f"{speaker}：{m['text']}\n"

    return (
        f"{REPLY_STYLE}\n\n"
        f"对方昵称：{contact}\n"
        f"最近聊天记录：\n{history}\n"
        f"请根据上面的聊天记录，生成一条合适的回复。"
        f"只输出回复内容本身，不要任何解释或前缀。"
    )


def wait_for_wb_reply(task_id: str) -> str:
    """
    等待 WorkBuddy 把回复写入 pending.json 的 wb_reply 字段。
    返回回复文本，超时返回空字符串。
    """
    deadline = time.time() + WB_TIMEOUT
    while time.time() < deadline:
        if PENDING_FILE.exists():
            try:
                task = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
                # 确认是同一个任务
                if task.get("id") != task_id:
                    log("  [警告] pending.json 任务 ID 已变更，放弃等待")
                    return ""
                if task.get("status") == "replied":
                    reply = task.get("wb_reply", "").strip()
                    if reply:
                        log(f"  [收到] WorkBuddy 回复: {reply}")
                        return reply
            except Exception:
                pass
        time.sleep(CHECK_INTERVAL)

    log(f"  [超时] {WB_TIMEOUT}s 内未收到 WorkBuddy 回复")
    return ""


def process_task(task: dict):
    """处理一个 pending 任务：构建 prompt → 等待回复 → 写出 reply.json"""
    task_id = task.get("id", "unknown")
    contact = task.get("contact", "对方")
    messages = task.get("messages", [])

    if not messages:
        log(f"[{task_id}] 消息列表为空，跳过")
        return

    log(f"[{task_id}] 联系人={contact}, 消息数={len(messages)}")

    prompt = build_prompt(contact, messages)

    # 把 prompt 写回 pending.json，WorkBuddy 读到后生成回复再写回
    task["wb_prompt"] = prompt
    task["status"] = "waiting_wb"
    PENDING_FILE.write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  [等待] 已写入 wb_prompt，等待 WorkBuddy 填充回复...")

    reply = wait_for_wb_reply(task_id)
    if not reply:
        log(f"  [失败] 未获得回复，任务 {task_id} 放弃")
        return

    # 写出 reply.json 供 wechat_monitor.py 读取
    result = {"reply": reply, "task_id": task_id}
    REPLY_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  [完成] reply.json 已写出: {reply}")


def main():
    COMM_DIR.mkdir(exist_ok=True)
    log("=" * 55)
    log("WorkBuddy 回复生成器  启动")
    log(f"监控目录: {COMM_DIR}")
    log("等待 wechat_monitor.py 写入任务...")
    log("=" * 55)

    last_task_id = None

    while True:
        try:
            if PENDING_FILE.exists():
                try:
                    task = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
                    task_id = task.get("id")
                    status  = task.get("status", "pending")

                    # 新任务（未处理过，且不是等待状态）
                    if (task_id != last_task_id
                            and status not in ("waiting_wb", "replied")):
                        last_task_id = task_id
                        log(f"发现新任务: {task_id}")
                        process_task(task)

                except json.JSONDecodeError:
                    pass   # 文件可能正在写入，下次再读
                except Exception as e:
                    log(f"[错误] {e}")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log("用户中止，退出")
            break


if __name__ == "__main__":
    main()
