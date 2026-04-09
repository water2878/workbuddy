import sys, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("wechat_monitor", "wechat_monitor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("Import OK")
except Exception:
    traceback.print_exc()
