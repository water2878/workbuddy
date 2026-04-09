"""
用 pywxdump 内置的 get_wx_info 获取key，但修复路径适配新版微信4.x
同时尝试多种搜索模式
"""
import psutil
import ctypes
import ctypes.wintypes
import os
import hashlib
import hmac
import struct

PROCESS_ALL_ACCESS = 0x1F0FFF
ReadProcessMemory = ctypes.windll.kernel32.ReadProcessMemory
OpenProcess = ctypes.windll.kernel32.OpenProcess
CloseHandle = ctypes.windll.kernel32.CloseHandle
VirtualQueryEx = ctypes.windll.kernel32.VirtualQueryEx

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("__alignment1", ctypes.wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.wintypes.DWORD),
        ("Protect", ctypes.wintypes.DWORD),
        ("Type", ctypes.wintypes.DWORD),
        ("__alignment2", ctypes.wintypes.DWORD),
    ]

def read_bytes(h_process, addr, size):
    buf = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    if ReadProcessMemory(h_process, ctypes.c_void_p(addr), buf, size, ctypes.byref(bytes_read)):
        return bytes(buf[:bytes_read.value])
    return None

def verify_key_real(key_bytes, db_path):
    """真正的SQLCipher key验证（兼容v3和v4）"""
    try:
        if not os.path.exists(db_path):
            return False
        with open(db_path, 'rb') as f:
            salt = f.read(16)
            page1 = f.read(4096 - 16)

        # SQLCipher v3 (旧版微信): SHA1, 64000 iterations
        dk = hashlib.pbkdf2_hmac('sha1', key_bytes, salt, 64000, dklen=32)
        mac_salt = bytes([x ^ 58 for x in salt])
        mac_key = hashlib.pbkdf2_hmac('sha1', dk, mac_salt, 2, dklen=32)
        
        hash_data = page1[:-32]
        stored_hash = page1[-32:-12]
        computed = hmac.new(mac_key, hash_data + struct.pack('<I', 1), hashlib.sha1).digest()
        if computed[:20] == stored_hash[:20]:
            return True

        # SQLCipher v4: SHA512, 256000 iterations
        dk4 = hashlib.pbkdf2_hmac('sha512', key_bytes, salt, 256000, dklen=32)
        mac_salt4 = bytes([x ^ 58 for x in salt])
        mac_key4 = hashlib.pbkdf2_hmac('sha512', dk4, mac_salt4, 2, dklen=64)
        hash_data4 = page1[:-64]
        stored_hash4 = page1[-64:-32]
        computed4 = hmac.new(mac_key4, hash_data4 + struct.pack('<I', 1), hashlib.sha512).digest()
        if computed4[:32] == stored_hash4[:32]:
            return True

        return False
    except Exception as e:
        return False

def search_keys_in_process(pid, db_paths, chunk_size=4*1024*1024):
    """搜索进程内存中的key"""
    h_process = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        return None
    
    addr = 0
    key_candidates = []
    regions = []
    
    mbi = MEMORY_BASIC_INFORMATION()
    while VirtualQueryEx(h_process, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        # MEM_COMMIT + (PAGE_READWRITE | PAGE_READONLY | PAGE_WRITECOPY)
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x02, 0x08) and mbi.RegionSize <= chunk_size:
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        if addr + mbi.RegionSize <= addr:
            break
        addr += mbi.RegionSize
        if addr > 0x7FFFFFFFFFFF:
            break
    
    print(f"PID={pid}: {len(regions)} 个可写内存区域待扫描")
    
    # 搜索若干关键字符串定位key区域
    keywords = [
        b"\\Msg\\MicroMsg",
        b"\\Msg\\micro",
        b"MicroMsg.db",
        b"SetDBKey",
        b"AccountInfo",
        b"sqlite_master",
    ]
    
    found_near = set()
    for base, size in regions:
        data = read_bytes(h_process, base, size)
        if not data:
            continue
        for kw in keywords:
            if kw.lower() in data.lower():
                found_near.add(base)
                break
    
    print(f"找到 {len(found_near)} 个包含关键字符串的区域")
    
    # 在这些区域附近搜索32字节高熵key
    for base in found_near:
        data = read_bytes(h_process, base, 4096 * 4)
        if not data:
            continue
        for i in range(0, len(data) - 32, 4):
            candidate = data[i:i+32]
            if len(set(candidate)) < 20:
                continue
            for db_path in db_paths:
                if verify_key_real(candidate, db_path):
                    CloseHandle(h_process)
                    print(f"✅ KEY FOUND near keyword region!")
                    return candidate.hex(), db_path
    
    # 如果上面没找到，全扫描可写内存
    print("关键字附近没找到，开始全量扫描可写内存...")
    for idx, (base, size) in enumerate(regions):
        if idx % 50 == 0:
            print(f"  进度: {idx}/{len(regions)}")
        data = read_bytes(h_process, base, size)
        if not data:
            continue
        for i in range(0, len(data) - 32, 8):
            candidate = data[i:i+32]
            if len(set(candidate)) < 22:
                continue
            for db_path in db_paths:
                if verify_key_real(candidate, db_path):
                    CloseHandle(h_process)
                    print(f"✅ KEY FOUND in full scan!")
                    return candidate.hex(), db_path
    
    CloseHandle(h_process)
    return None, None

# 找所有DB路径
wx_files = r"C:\Users\Lenovo\Documents\WeChat Files"
all_db_paths = []
for wxid in os.listdir(wx_files):
    db = os.path.join(wx_files, wxid, "Msg", "MicroMsg.db")
    if os.path.exists(db):
        all_db_paths.append(db)

print(f"找到 {len(all_db_paths)} 个数据库")

# 按内存大小排序的Weixin.exe进程
weixin_procs = []
for p in psutil.process_iter(['pid', 'name', 'memory_info']):
    try:
        if p.info['name'] == 'Weixin.exe':
            mem = p.info['memory_info'].rss
            weixin_procs.append((mem, p.info['pid']))
    except:
        pass

weixin_procs.sort(reverse=True)
print(f"Weixin.exe进程: {[(m//1024//1024, pid) for m, pid in weixin_procs]}")

for mem, pid in weixin_procs:
    if mem < 10 * 1024 * 1024:  # 跳过小于10MB的
        continue
    print(f"\n正在扫描 PID={pid} ({mem//1024//1024}MB)...")
    key, matched_db = search_keys_in_process(pid, all_db_paths)
    if key:
        print(f"\n{'='*50}")
        print(f"KEY: {key}")
        print(f"DB:  {matched_db}")
        print(f"{'='*50}")
        
        # 保存key到文件
        wxid = matched_db.split("\\")[-3]
        with open(f"wx_key_{wxid}.txt", "w") as f:
            f.write(f"wxid: {wxid}\nkey: {key}\ndb: {matched_db}\n")
        print(f"已保存到 wx_key_{wxid}.txt")
        break
else:
    print("\n所有进程扫描完毕，未找到key")
