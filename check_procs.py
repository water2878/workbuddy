import psutil
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if 'python' in (p.info['name'] or '').lower():
            print(p.info['pid'], p.info['cmdline'])
    except Exception:
        pass
