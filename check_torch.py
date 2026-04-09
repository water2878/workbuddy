import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sys
print("Python:", sys.version)
print("Python path:", sys.executable)

# 检查 torch
try:
    import torch
    print("torch OK:", torch.__version__)
except Exception as e:
    print("torch FAIL:", e)

# 检查 VC++ 运行库
import os
vc_paths = [
    r"C:\Windows\System32\vcruntime140.dll",
    r"C:\Windows\System32\vcruntime140_1.dll",
    r"C:\Windows\System32\msvcp140.dll",
    r"C:\Windows\System32\concrt140.dll",
]
print("\nVC++ 运行库:")
for p in vc_paths:
    print(f"  {'✅' if os.path.exists(p) else '❌'} {p}")

# 检查 paddlepaddle
try:
    import paddle
    print("\npaddle OK:", paddle.__version__)
except Exception as e:
    print("\npaddle FAIL:", e)
