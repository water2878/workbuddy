@echo off
chcp 65001 >nul
cd /d C:\Users\Lenovo\WorkBuddy\Claw
echo 正在启动微信聊天记录批量导出...
echo 请勿操作鼠标和键盘，等待脚本自动完成
echo.
python export_chat.py
echo.
echo 导出完成！
pause
