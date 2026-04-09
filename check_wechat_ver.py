import os, glob

paths = [
    r'C:\Program Files\Tencent\WeChat',
    r'C:\Program Files (x86)\Tencent\WeChat',
    r'C:\Users\Lenovo\AppData\Roaming\Tencent\WeChat',
]

for p in paths:
    if os.path.exists(p):
        print(f"找到目录: {p}")
        for f in os.listdir(p):
            if f.endswith('.exe'):
                full = os.path.join(p, f)
                size = os.path.getsize(full)
                print(f"  {f}  ({size//1024} KB)")

# 用文件版本信息
import struct, ctypes
def get_version(filepath):
    try:
        info = ctypes.windll.version.GetFileVersionInfoSizeW(filepath, None)
        if not info:
            return None
        buf = ctypes.create_string_buffer(info)
        ctypes.windll.version.GetFileVersionInfoW(filepath, None, info, buf)
        ver_ptr = ctypes.c_void_p()
        ver_len = ctypes.c_uint()
        ctypes.windll.version.VerQueryValueW(buf, '\\', ctypes.byref(ver_ptr), ctypes.byref(ver_len))
        ver = ctypes.cast(ver_ptr, ctypes.POINTER(ctypes.c_uint16 * 8)).contents
        return f"{ver[1]}.{ver[0]}.{ver[3]}.{ver[2]}"
    except:
        return None

# 搜索所有可能路径
for root in [r'C:\Program Files', r'C:\Program Files (x86)', r'C:\Users\Lenovo\AppData']:
    for f in glob.glob(os.path.join(root, '**', 'WeChatAppEx.exe'), recursive=True):
        v = get_version(f)
        print(f"WeChatAppEx: {f}  版本: {v}")
    for f in glob.glob(os.path.join(root, '**', 'WeChat.exe'), recursive=True):
        v = get_version(f)
        print(f"WeChat.exe: {f}  版本: {v}")
