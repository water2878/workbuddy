import shutil, pathlib
src  = pathlib.Path(r'C:/Users/Lenovo/WorkBuddy/Claw')
dst  = pathlib.Path(r'C:/Users/Lenovo/.workbuddy/skills/wechat-chat-exporter/scripts')
dst.mkdir(parents=True, exist_ok=True)
for f in ['get_contacts.py','export_chat.py','wechat_all_in_one.py','dedup_contacts.py']:
    shutil.copy(src/f, dst/f)
    print(f'copied {f}')
print('all done')
