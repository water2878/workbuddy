"""
静默发送消息（无控制台窗口弹窗）
用法: silent_send.py "客户名称" "消息内容"
"""
import sys
import os
import subprocess
from datetime import datetime

def silent_send(contact, message):
    """使用 CREATE_NO_WINDOW 标志静默执行 send_reply.py"""
    script = os.path.join(os.path.dirname(__file__), "send_reply.py")
    python = sys.executable
    
    # CREATE_NO_WINDOW = 0x08000000 - 不创建控制台窗口
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    result = subprocess.run(
        [python, script, contact, message],
        capture_output=True,
        text=True,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        startupinfo=startupinfo
    )
    
    output = (result.stdout or "") + (result.stderr or "")
    success = "✅ 发送成功" in result.stdout
    
    return success, output.strip()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python silent_send.py \"客户名称\" \"消息内容\"")
        sys.exit(1)
    
    contact, message = sys.argv[1], sys.argv[2]
    success, output = silent_send(contact, message)
    
    if success:
        print(f"✅ 发送成功 -> {contact}")
    else:
        print(f"❌ 发送失败 -> {contact}")
        print(output)
