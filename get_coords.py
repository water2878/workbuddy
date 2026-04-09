import pyautogui
import time

# 截全屏，找任务栏微信图标
screenshot = pyautogui.screenshot()
screenshot.save(r"c:\Users\Lenovo\WorkBuddy\Claw\fullscreen.png")
print("Full screen screenshot saved")
print("Screen size:", pyautogui.size())
