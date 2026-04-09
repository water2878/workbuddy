import time
import pyautogui
import pyperclip
import sys
import ctypes
import ctypes.wintypes
import subprocess
import os

CONTACT = sys.argv[1] if len(sys.argv) > 1 else "filehelper"
FILE_PATH = sys.argv[2] if len(sys.argv) > 2 else ""

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = False

def find_and_activate_wechat():
    hwnd = ctypes.windll.user32.FindWindowW(None, "\u5fae\u4fe1")
    if hwnd == 0:
        hwnd = ctypes.windll.user32.FindWindowW(None, "WeChat")
    if hwnd == 0:
        print("ERROR: WeChat window not found!")
        sys.exit(1)
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(1)
    print("OK WeChat activated hwnd=" + str(hwnd))
    return hwnd

hwnd = find_and_activate_wechat()

rect = ctypes.wintypes.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
win_x = rect.left
win_y = rect.top
win_w = rect.right - rect.left
win_h = rect.bottom - rect.top

# 1. Ctrl+F 搜索联系人
pyautogui.hotkey('ctrl', 'f')
time.sleep(0.8)
pyperclip.copy(CONTACT)
pyautogui.hotkey('ctrl', 'v')
time.sleep(1.2)

# 2. 点击第一行结果
result_x = win_x + int(win_w * 0.18)
result_y = win_y + 100
pyautogui.click(result_x, result_y)
time.sleep(1.5)
print("Clicked 1st result")

# 3. 点击输入框
input_x = win_x + win_w // 2
input_y = win_y + int(win_h * 0.88)
pyautogui.click(input_x, input_y)
time.sleep(0.5)

# 4. 使用 Ctrl+V 粘贴文件（先用 PowerShell 将文件放入剪贴板）
print("Copying file to clipboard: " + FILE_PATH)
ps_cmd = '''
Add-Type -AssemblyName System.Windows.Forms
$files = New-Object System.Collections.Specialized.StringCollection
$files.Add("%s")
[System.Windows.Forms.Clipboard]::SetFileDropList($files)
Write-Host "File copied to clipboard"
''' % FILE_PATH
result = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
print(result.stdout.strip())
time.sleep(0.5)

# 5. 粘贴文件到微信输入框
pyautogui.click(input_x, input_y)
time.sleep(0.3)
pyautogui.hotkey('ctrl', 'v')
time.sleep(1.5)

# 截图确认
screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
screenshot.save(r"c:\Users\Lenovo\WorkBuddy\Claw\wechat_file_send.png")
print("SCREENSHOT_SAVED")

# 6. 回车发送
pyautogui.press('enter')
time.sleep(0.8)
print("File sent: " + FILE_PATH + " -> " + CONTACT)
