import os
from pathlib import Path

export_dir = Path(r'C:\Users\Lenovo\Desktop\微信导出_AiLy 李15502540306_20260316_125450')
raw_dir = export_dir / 'raw_screenshots'

print(f"导出目录内容:")
for f in sorted(export_dir.iterdir()):
    if f.is_file():
        print(f"  {f.name} ({f.stat().st_size//1024}KB)")
    else:
        print(f"  [{f.name}/]")

print(f"\n截图列表:")
if raw_dir.exists():
    shots = sorted(raw_dir.glob('*.png'))
    print(f"  共 {len(shots)} 张截图")
    for s in shots[:5]:
        print(f"  {s.name} ({s.stat().st_size//1024}KB)")
    if len(shots) > 5:
        print(f"  ... (还有 {len(shots)-5} 张)")

# 查看txt内容
txt_files = list(export_dir.glob('*.txt'))
if txt_files:
    print(f"\nTXT内容预览 ({txt_files[0].name}):")
    with open(txt_files[0], encoding='utf-8') as f:
        content = f.read()
    print(f"  总字符数: {len(content)}")
    print(f"  前500字符:")
    print(content[:500])
