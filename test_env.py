import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

"""
通过搜索 SetDBKey 字符串在内存中定位微信数据库key
"""
import psutil
import ctypes
import ctypes.wintypes as wintypes
import os
import hashlib
import hmac as hmac_mod

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
OpenProcess = kernel32.OpenProcess
OpenProcess.restype = wintypes.HANDLE
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
CloseHandle = kernel32.CloseHandle
ReadProcessMemory = kernel32.ReadProcessMemory
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
void_p = ctypes.c_void_p

def read_bytes(h_proc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    if ReadProcessMemory(h_proc, void_p(addr), buf, size, ctypes.byref(br)) == 0:
        return None
    return bytes(buf[:br.value])

def search_mem(h_proc, pattern, start, end, max_num=20):
    found = []
    addr = start
    buf_size = 0x10000
    buf = ctypes.create_string_buffer(buf_size)
    while addr < end and len(found) < max_num:
        br = ctypes.c_size_t(0)
        ok = ReadProcessMemory(h_proc, void_p(addr), buf, buf_size, ctypes.byref(br))
        if ok and br.value > 0:
            data = bytes(buf[:br.value])
            off = 0
            while True:
                idx = data.find(pattern, off)
                if idx == -1: break
                found.append(addr + idx)
                if len(found) >= max_num: break
                off = idx + 1
        addr += buf_size
    return found

def verify_key_pywxdump(key: bytes, db_path: str) -> bool:
    """使用pywxdump相同的SQLCipher3验证方法"""
    if not os.path.exists(db_path) or len(key) != 32:
        return False
    try:
        with open(db_path, 'rb') as f:
            blist = f.read(5000)
        salt = blist[:16]
        KEY_SIZE = 32
        DEFAULT_ITER = 64000
        DEFAULT_PAGESIZE = 4096
        pk = hashlib.pbkdf2_hmac("sha1", key, salt, DEFAULT_ITER, KEY_SIZE)
        first = blist[16:DEFAULT_PAGESIZE]
        mac_salt = bytes([(salt[i] ^ 58) for i in range(16)])
        pk2 = hashlib.pbkdf2_hmac("sha1", pk, mac_salt, 2, KEY_SIZE)
        h = hmac_mod.new(pk2, first[:-32], hashlib.sha1)
        h.update(b'\x01\x00\x00\x00')
        return h.digest() == first[-32:-12]
    except Exception as e:
        return False

# 找目标进程
target_pid = None
max_mem = 0
for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
    try:
        if proc.info['name'] == 'Weixin.exe':
            mem = proc.info['memory_info'].rss if proc.info['memory_info'] else 0
            if mem > max_mem:
                max_mem = mem
                target_pid = proc.info['pid']
    except Exception:
        pass

print(f"目标PID: {target_pid}, 内存: {max_mem//1024//1024}MB")

# 获取Weixin.dll范围
proc = psutil.Process(target_pid)
dll_start, dll_end = 0x7FFFFFFFFFFFFFFF, 0
for m in proc.memory_maps(grouped=False):
    path = getattr(m, 'path', '') or ''
    if 'weixin.dll' in path.lower():
        addr = int(m.addr, 16)
        if addr < dll_start: dll_start = addr
        if addr > dll_end: dll_end = addr
dll_end += 0x1000000  # 加16MB

print(f"Weixin.dll 范围: 0x{dll_start:016x} - 0x{dll_end:016x}")

# 准备MicroMsg.db路径
wx_files = r"C:\Users\Lenovo\Documents\WeChat Files"
micromsg_paths = []
for wxid_dir in os.listdir(wx_files):
    if wxid_dir.startswith('wxid_') or wxid_dir == 'leenluo':
        db = os.path.join(wx_files, wxid_dir, 'Msg', 'MicroMsg.db')
        if os.path.exists(db):
            micromsg_paths.append(db)
print(f"MicroMsg.db 路径: {micromsg_paths}")

h = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, target_pid)
if not h:
    print(f"无法打开进程, error={ctypes.get_last_error()}")
    sys.exit(1)

print("\n=== 搜索 SetDBKey 字符串 ===")
# 在全进程内存搜索（不限于Weixin.dll）
patterns = [b'SetDBKey', b'setDBKey', b'setCipherKey', b'set_cipher_key']
for pat in patterns:
    addrs = search_mem(h, pat, 0x10000, 0x7FFFFFFF0000, max_num=5)
    print(f"  {pat!r}: {[hex(a) for a in addrs[:5]]}")
    # 打印周围内容
    for addr in addrs[:2]:
        ctx = read_bytes(h, max(0, addr-50), 150)
        if ctx:
            print(f"    0x{addr:016x}: ...{ctx!r}...")

print("\n=== 搜索 wcdb 相关字符串 ===")
wcdb_pats = [b'wcdb', b'WCDB', b'WCDBKey', b'setCipherKey']
for pat in wcdb_pats:
    addrs = search_mem(h, pat, dll_start, dll_end, max_num=3)
    if addrs:
        print(f"  {pat!r}: {[hex(a) for a in addrs]}")

CloseHandle(h)
