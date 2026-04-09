import shutil
import os

src = r"C:\Users\Lenovo\Desktop\wechat-automation"
dst = r"C:\Users\Lenovo\WorkBuddy\Claw"

for item in os.listdir(src):
    s = os.path.join(src, item)
    d = os.path.join(dst, item)
    if os.path.isdir(s):
        if os.path.exists(d):
            shutil.rmtree(d)
        shutil.copytree(s, d)
        print(f"Copied dir: {item}")
    else:
        shutil.copy2(s, d)
        print(f"Copied file: {item}")

print("\nDone!")
