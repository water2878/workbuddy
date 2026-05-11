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

_stage = [0]


def log_stage(msg):
    _stage[0] += 1
    print(f"\n[{_stage[0]}/3] {msg}")

def log_ok(msg):
    print(f"    ✓ {msg}")

def log_info(msg):
    print(f"      {msg}")


_output_threads = {}


def stream_output(proc, label):
    """Stream subprocess output with prefix, with auto-restart on failure"""
    thread_name = threading.current_thread().name
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue

            line = line.strip()
            if not line:
                continue

            if 'GET /static/' in line or 'GET /favicon.ico' in line:
                continue

            try:
                sys.stdout.write(f"[{label}] {line}\n")
                sys.stdout.flush()
            except UnicodeEncodeError:
                safe_line = line.encode('utf-8', errors='replace').decode('utf-8')
                sys.stdout.write(f"[{label}] {safe_line}\n")
                sys.stdout.flush()
            except (OSError, BrokenPipeError):
                break
    except Exception as e:
        print(f"[{label}] 输出流异常: {e}", flush=True)

    if proc.poll() is None:
        print(f"[{label}] ⚠ 输出线程退出但进程仍在运行，3秒后重启输出线程...", flush=True)
        time.sleep(3)
        if proc.poll() is None:
            new_thread = threading.Thread(
                target=stream_output, args=(proc, label),
                daemon=True, name=f"stream-{label}"
            )
            new_thread.start()
            _output_threads[label] = new_thread
            print(f"[{label}] ✓ 输出线程已重启", flush=True)


def kill_existing_processes():
    import psutil
    killed = []
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if ('weflow_wb_bridge.py' in cmdline or
                'start_all.py' in cmdline or
                (proc.info['name'] == 'python.exe' and 'core/app.py' in cmdline)):
                proc.terminate()
                killed.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        log_info(f"已清理旧进程: {killed}")
        time.sleep(1)

def print_banner():
    print("\n" + "=" * 50)
    print("           Claw Service Launcher")
    print("=" * 50)

def print_services():
    print("\n" + "-" * 50)
    print("  服务地址:")
    print("    • API:     http://127.0.0.1:5032")
    print("    • WeFlow:  http://127.0.0.1:5031")
    print("-" * 50)
    print("\n  按 Ctrl+C 停止所有服务\n")

def main():
    print_banner()

    log_stage("清理旧进程...")
    kill_existing_processes()
    log_ok("清理完成")

    flask_cmd = [sys.executable, "-u", os.path.join(ROOT, "core", "app.py")]
    bridge_cmd = [sys.executable, "-u", os.path.join(ROOT, "weflow_wb_bridge.py")]

    log_stage("启动 API 服务...")
    log_info(f"命令: {' '.join(flask_cmd)}")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    flask = subprocess.Popen(
        flask_cmd, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=env,
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    procs.append(flask)

    flask_thread = threading.Thread(
        target=stream_output, args=(flask, "API"),
        daemon=True, name="stream-API"
    )
    flask_thread.start()
    _output_threads["API"] = flask_thread
    log_info("输出线程已启动")

    time.sleep(2)
    log_ok("API 服务已启动")

    log_stage("启动 WeFlow 桥接...")
    log_info(f"命令: {' '.join(bridge_cmd)}")

    bridge = subprocess.Popen(
        bridge_cmd, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=env,
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    procs.append(bridge)

    bridge_thread = threading.Thread(
        target=stream_output, args=(bridge, "Bridge"),
        daemon=True, name="stream-Bridge"
    )
    bridge_thread.start()
    _output_threads["Bridge"] = bridge_thread
    log_info("输出线程已启动")

    time.sleep(1)
    log_ok("WeFlow 桥接已启动")

    print_services()

    try:
        while True:
            for p in procs:
                ret = p.poll()
                if ret is not None:
                    print(f"\n[!] {('API' if p is flask else 'Bridge')} 已退出 (code={ret})")
                    raise SystemExit

            for label, thread in list(_output_threads.items()):
                if not thread.is_alive():
                    proc = flask if label == "API" else bridge
                    if proc.poll() is None:
                        print(f"[{label}] ⚠ 输出线程已死亡，正在重启...", flush=True)
                        new_thread = threading.Thread(
                            target=stream_output, args=(proc, label),
                            daemon=True, name=f"stream-{label}"
                        )
                        new_thread.start()
                        _output_threads[label] = new_thread
                        print(f"[{label}] ✓ 输出线程已重启", flush=True)

            time.sleep(2)
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
