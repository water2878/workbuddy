import os, glob

# 检查账号目录
wx_files = r"C:\Users\Lenovo\Documents\WeChat Files"
accounts = os.listdir(wx_files)
print("所有账号目录:")
for acc in accounts:
    acc_path = os.path.join(wx_files, acc)
    if os.path.isdir(acc_path):
        micro_db = os.path.join(acc_path, "Msg", "MicroMsg.db")
        msg_db = os.path.join(acc_path, "Msg", "Multi", "MSG0.db")
        print(f"  {acc}")
        print(f"    MicroMsg.db: {'存在 ' + str(os.path.getsize(micro_db)//1024) + 'KB' if os.path.exists(micro_db) else '不存在'}")
        print(f"    MSG0.db:     {'存在 ' + str(os.path.getsize(msg_db)//1024) + 'KB' if os.path.exists(msg_db) else '不存在'}")

# 检查微信进程
import psutil
print("\n微信进程:")
for p in psutil.process_iter(['pid', 'name', 'memory_info']):
    try:
        if 'weixin' in p.info['name'].lower() or 'wechat' in p.info['name'].lower():
            mem = p.info['memory_info'].rss // 1024 // 1024
            print(f"  PID={p.info['pid']} {p.info['name']} {mem}MB")
    except:
        pass
