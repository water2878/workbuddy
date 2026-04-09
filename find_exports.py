import os
base = r'C:\Users\Lenovo\Desktop'
dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
for d in sorted(dirs):
    print(d)
