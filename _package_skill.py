import zipfile, pathlib, os

skill = pathlib.Path('C:/Users/Lenovo/.workbuddy/skills/wechat-chat-exporter')
out = pathlib.Path('C:/Users/Lenovo/WorkBuddy/Claw/wechat-chat-exporter.zip')

# 只打包需要的文件，跳过示例文件
SKIP_FILES = {'example.py', 'api_reference.md', 'example_asset.txt'}

with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in skill.rglob('*'):
        if f.is_file() and f.name not in SKIP_FILES:
            arcname = f.relative_to(skill.parent)
            z.write(f, arcname)
            print(f'  + {arcname}')

print(f'\n打包完成: {out}')
