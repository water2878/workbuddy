from PIL import Image
img = Image.open(r'c:\Users\Lenovo\WorkBuddy\Claw\wechat_screenshot.png')
print('Size:', img.size)
img.save(r'c:\Users\Lenovo\WorkBuddy\Claw\wechat_full.png')
print('Saved full screenshot')
