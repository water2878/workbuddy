import subprocess, sys, time
proc = subprocess.Popen(
    [sys.executable, "wechat_monitor.py"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, encoding="utf-8", errors="replace",
    cwd=r"C:\Users\Lenovo\WorkBuddy\Claw"
)
time.sleep(12)
proc.terminate()
out, _ = proc.communicate(timeout=5)
print(out[:3000])
