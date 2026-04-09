"""
批量OCR识别图片并整理为QA文档
使用PaddleOCR识别所有截图中的文字，提取问答内容
"""
import sys
import os
from pathlib import Path

# 添加路径
sys.path.insert(0, r'C:\Users\Lenovo\.workbuddy\skills\wechat-automation')

try:
    from paddleocr import PaddleOCR
    import cv2
    import numpy as np
except ImportError:
    print("正在安装PaddleOCR...")
    os.system("pip install paddlepaddle paddleocr")
    from paddleocr import PaddleOCR
    import cv2
    import numpy as np

import re
from datetime import datetime

# 初始化OCR
print("正在初始化PaddleOCR，首次运行会下载模型，请耐心等待...")
ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

def find_image_files():
    """查找所有图片文件"""
    # 常见图片存放路径
    search_paths = [
        r"C:\Users\Lenovo\Downloads",
        r"C:\Users\Lenovo\Desktop",
        r"C:\Users\Lenovo\WorkBuddy\Claw",
        r"C:\Users\Lenovo\AppData\Local\Temp"
    ]
    
    image_files = []
    pattern = re.compile(r"image_1773808577751_[a-f0-9-]+\.png")
    
    for search_path in search_paths:
        if os.path.exists(search_path):
            print(f"正在搜索: {search_path}")
            for root, dirs, files in os.walk(search_path):
                for file in files:
                    if pattern.match(file):
                        full_path = os.path.join(root, file)
                        image_files.append(full_path)
                        print(f"找到图片: {full_path}")
    
    # 如果没找到，提示用户手动指定路径
    if not image_files:
        print("\n未找到图片文件！")
        print("\n请手动指定图片文件夹路径（例如：C:\\Users\\Lenovo\\Desktop\\图片）")
        custom_path = input("请输入图片文件夹路径（直接回车跳过）: ").strip()
        
        if custom_path and os.path.exists(custom_path):
            print(f"正在搜索: {custom_path}")
            for root, dirs, files in os.walk(custom_path):
                for file in files:
                    if pattern.match(file):
                        full_path = os.path.join(root, file)
                        image_files.append(full_path)
                        print(f"找到图片: {full_path}")
        elif custom_path:
            print(f"路径不存在: {custom_path}")
    
    return image_files

def extract_qa_from_text(text):
    """从OCR识别的文本中提取问答对"""
    qa_pairs = []
    lines = text.split('\n')
    
    current_q = ""
    current_a = ""
    in_question = False
    in_answer = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 识别问题（以Q:、问、？结尾等）
        if line.startswith('Q:') or line.startswith('问') or line.endswith('？') or line.endswith('?') or '能不能' in line or '可以' in line or '吗' in line:
            # 如果之前有答案，保存上一条QA
            if current_q and current_a:
                qa_pairs.append((current_q, current_a))
            current_q = line
            current_a = ""
            in_question = True
            in_answer = False
        # 识别答案（以A:、答、。结尾等）
        elif line.startswith('A:') or line.startswith('答') or line.endswith('。') or (in_question and not line.endswith('？')):
            if current_q:
                if current_a:
                    current_a += " " + line
                else:
                    current_a = line
            in_question = False
            in_answer = True
        else:
            # 如果是连续的文本，追加到当前QA
            if in_answer and current_a:
                current_a += " " + line
            elif in_question and current_q:
                current_q += " " + line
    
    # 保存最后一条QA
    if current_q and current_a:
        qa_pairs.append((current_q, current_a))
    
    return qa_pairs

def recognize_image(image_path):
    """识别单张图片"""
    try:
        print(f"\n正在识别: {os.path.basename(image_path)}")
        result = ocr.ocr(image_path, cls=True)
        
        if not result or not result[0]:
            return ""
        
        text_lines = []
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0] if isinstance(line[1], tuple) else str(line[1])
                text_lines.append(text)
        
        full_text = "\n".join(text_lines)
        print(f"识别完成，共 {len(text_lines)} 行文字")
        return full_text
    except Exception as e:
        print(f"识别失败: {e}")
        return ""

def main():
    # 查找图片
    print("=" * 60)
    print("批量OCR识别 - 聊天QA提取")
    print("=" * 60)
    
    image_files = find_image_files()
    
    if not image_files:
        print("\n[错误] 未找到任何匹配的图片文件！")
        print("请确保图片文件已下载到本地")
        return
    
    print(f"\n找到 {len(image_files)} 张图片，开始批量识别...")
    
    # 识别所有图片
    all_qa_pairs = []
    
    for i, img_path in enumerate(image_files, 1):
        print(f"\n[{i}/{len(image_files)}] ", end="")
        text = recognize_image(img_path)
        
        if text:
            qa_pairs = extract_qa_from_text(text)
            if qa_pairs:
                all_qa_pairs.extend(qa_pairs)
                print(f"提取到 {len(qa_pairs)} 组QA")
        
        # 每处理10张图片保存一次中间结果
        if i % 10 == 0:
            save_progress(all_qa_pairs, i)
    
    # 保存最终结果
    save_final_result(all_qa_pairs)
    
    print("\n" + "=" * 60)
    print(f"[完成] 全部完成！共识别 {len(image_files)} 张图片，提取 {len(all_qa_pairs)} 组QA")
    print("=" * 60)

def save_progress(qa_pairs, count):
    """保存中间进度"""
    desktop = Path.home() / "Desktop"
    progress_file = desktop / f"聊天QA_临时进度_{count}.md"
    
    with open(progress_file, 'w', encoding='utf-8') as f:
        f.write(f"# 聊天QA提取 - 临时进度 ({count} 张图片)\n\n")
        f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for i, (q, a) in enumerate(qa_pairs, 1):
            f.write(f"## Q{i}: {q}\n\n")
            f.write(f"**A:** {a}\n\n")
            f.write("---\n\n")
    
    print(f"进度已保存: {progress_file.name}")

def save_final_result(qa_pairs):
    """保存最终结果"""
    desktop = Path.home() / "Desktop"
    output_file = desktop / "聊天QA完整版.md"
    
    # 去重
    unique_qa = []
    seen = set()
    for q, a in qa_pairs:
        key = (q.strip(), a.strip())
        if key not in seen:
            seen.add(key)
            unique_qa.append((q, a))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 聊天QA完整版\n\n")
        f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> 图片来源: 微信聊天记录截图\n")
        f.write(f"> 共提取: {len(unique_qa)} 组QA (已去重)\n\n")
        f.write("---\n\n")
        
        # 按主题分类
        categories = categorize_qa(unique_qa)
        
        for category, qa_list in categories.items():
            if qa_list:
                f.write(f"## {category}\n\n")
                for i, (q, a) in enumerate(qa_list, 1):
                    f.write(f"### Q{i}: {q}\n\n")
                    f.write(f"**A:** {a}\n\n")
                f.write("---\n\n")
        
        # 未分类的QA
        if categories["其他问题"]:
            f.write("## 其他问题\n\n")
            for i, (q, a) in enumerate(categories["其他问题"], 1):
                f.write(f"### Q{i}: {q}\n\n")
                f.write(f"**A:** {a}\n\n")
    
    print(f"\n[成功] 最终结果已保存到: {output_file}")

def categorize_qa(qa_pairs):
    """按主题分类QA"""
    categories = {
        "产品规格": [],
        "价格与起订量": [],
        "生产与发货": [],
        "现货情况": [],
        "认证与资料": [],
        "其他问题": []
    }
    
    for q, a in qa_pairs:
        q_lower = q.lower()
        a_lower = a.lower()
        
        if any(keyword in q_lower for keyword in ['规格', '参数', '尺寸', '重量', '材质', '承重', 'mm', 'kg']):
            categories["产品规格"].append((q, a))
        elif any(keyword in q_lower for keyword in ['价格', '多少钱', '起订', '单价', '运费']):
            categories["价格与起订量"].append((q, a))
        elif any(keyword in q_lower for keyword in ['生产', '发货', '下单', '付款', '安排']):
            categories["生产与发货"].append((q, a))
        elif any(keyword in q_lower for keyword in ['现货', '库存', '成品', '组装']):
            categories["现货情况"].append((q, a))
        elif any(keyword in q_lower for keyword in ['认证', '图册', '资料', 'pdf', 'ppt']):
            categories["认证与资料"].append((q, a))
        else:
            categories["其他问题"].append((q, a))
    
    return categories

if __name__ == "__main__":
    main()
