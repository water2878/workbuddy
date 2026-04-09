import importlib
libs = ["pyautogui", "pyperclip", "PIL", "easyocr", "rapidocr_onnxruntime", "win32gui", "mss"]
for lib in libs:
    try:
        importlib.import_module(lib)
        print(f"  [OK]  {lib}")
    except ImportError:
        print(f"  [MISS] {lib}")
