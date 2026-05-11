#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claw Launcher - Run Flask API + WeFlow Bridge in single window
Press Ctrl+C to stop all services
"""
import subprocess
import sys
import os
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
procs = []

# 启动阶段计数器
_stage = [0]

def log_stage(msg):
    """输出启动阶段信息"""
    _stage[0] += 1
    print(f"\n[{_stage[0]}/3] {msg}")

def log_ok(msg):
    """输出成功信息"""
    print(f"    ✓ {msg}")

def log_info(msg):
    """输出普通信息"""
    print(f"      {msg}")

def stream_output(proc, label):
    """Stream subprocess output with prefix"""
    try:
        while True:
            # 使用更可靠的方式读取输出
            line = proc.stdout.readline()
            if not line:
                # 进程结束
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue

            line = line.strip()
            if not line:
                continue

            # 过滤掉 Flask 的静态文件请求日志
            if 'GET /static/' in line or 'GET /favicon.ico' in line:
                continue

            try:
                sys.stdout.write(f"[{label}] {line}\n")
                sys.stdout.flush()
            except UnicodeEncodeError:
                # 编码错误时尝试用替代字符
                safe_line = line.encode('utf-8', errors='replace').decode('utf-8')
                sys.stdout.write(f"[{label}] {safe_line}\n")
                sys.stdout.flush()
    except Exception as e:
        # 输出错误信息以便调试
        print(f"[{label}] 输出流异常: {e}")
        pass

def kill_existing_processes():
    """Kill existing weflow_wb_bridge and app.py processes"""
    import psutil
    killed = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'weflow_wb_bridge.py' in cmdline or (proc.info['name'] == 'python.exe' and 'core/app.py' in cmdline):
                proc.terminate()
                killed.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        log_info(f"已清理旧进程: {killed}")
        time.sleep(1)

def print_banner():
    """Print startup banner"""
    print("\n" + "=" * 50)
    print("           Claw Service Launcher")
    print("=" * 50)

def print_services():
    """Print running services info"""
    print("\n" + "-" * 50)
    print("  服务地址:")
    print("    • API:     http://127.0.0.1:5032")
    print("    • WeFlow:  http://127.0.0.1:5031")
    print("-" * 50)
    print("\n  按 Ctrl+C 停止所有服务\n")

def main():
    print_banner()

    # 1. Kill old processes
    log_stage("清理旧进程...")
    kill_existing_processes()
    log_ok("清理完成")

    # Flask API Server
    flask_cmd = [sys.executable, "-u", os.path.join(ROOT, "core", "app.py")]

    # WeFlow -> WorkBuddy Bridge
    bridge_cmd = [sys.executable, "-u", os.path.join(ROOT, "weflow_wb_bridge.py")]

    # 2. Start Flask
    log_stage("启动 API 服务...")
    log_info(f"命令: {' '.join(flask_cmd)}")

    # 使用环境变量强制 UTF-8 编码
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    flask = subprocess.Popen(
        flask_cmd, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=env,
        bufsize=1,  # 行缓冲
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    procs.append(flask)

    # 启动输出流线程
    flask_thread = threading.Thread(target=stream_output, args=(flask, "API"), daemon=True)
    flask_thread.start()
    log_info("输出线程已启动")

    time.sleep(2)
    log_ok("API 服务已启动")

    # 3. Start Bridge
    log_stage("启动 WeFlow 桥接...")
    log_info(f"命令: {' '.join(bridge_cmd)}")

    bridge = subprocess.Popen(
        bridge_cmd, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=env,
        bufsize=1,  # 行缓冲
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    procs.append(bridge)

    bridge_thread = threading.Thread(target=stream_output, args=(bridge, "Bridge"), daemon=True)
    bridge_thread.start()
    log_info("输出线程已启动")

    time.sleep(1)
    log_ok("WeFlow 桥接已启动")

    print_services()

    # Wait for any process to exit
    try:
        while True:
            for p in procs:
                ret = p.poll()
                if ret is not None:
                    print(f"\n[!] {('API' if p is flask else 'Bridge')} 已退出 (code={ret})")
                    raise SystemExit
            time.sleep(0.5)
    except (KeyboardInterrupt, SystemExit):
        print("\n" + "-" * 50)
        print("  正在停止所有服务...")
        print("-" * 50)
        for p in procs:
            if p.poll() is None:
                p.terminate()
        time.sleep(1)
        for p in procs:
            if p.poll() is None:
                p.kill()
        print("  ✓ 所有服务已停止")


if __name__ == "__main__":
    main()
