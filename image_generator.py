"""
微信消息图片生成模块
用于生成格式化的消息图片，解决微信排版限制
"""
from PIL import Image, ImageDraw, ImageFont
import os


def create_schedule_image(title, period, goal, days, milestones, footer=""):
    """
    创建项目时间安排图片（高度自适应）
    
    参数:
        title: 标题
        period: 项目周期
        goal: 项目目标
        days: 每日安排列表 [(日期, [任务列表]), ...]
        milestones: 关键节点列表
        footer: 底部文字
    
    返回:
        图片保存路径
    """
    # 先计算内容高度
    width = 800
    line_height = 32  # 每行高度
    header_height = 60  # 标题区域
    day_header_height = 40  # 日期标题
    separator_height = 50  # 分隔线+间距
    footer_height = 80 if footer else 30  # 底部区域
    
    # 计算总高度
    total_lines = 0
    for day, tasks in days:
        total_lines += 1 + len(tasks)  # 日期标题 + 任务数
    total_lines += len(milestones)  # 关键节点
    
    height = header_height + total_lines * line_height + len(days) * separator_height + footer_height + 100  # 额外留白
    
    # 颜色配置
    bg_color = (255, 255, 255)
    text_color = (0, 0, 0)
    accent_color = (0, 150, 136)
    line_color = (200, 200, 200)
    
    # 创建图片
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # 加载字体
    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 36)
        font_header = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 28)
        font_text = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
    except:
        font_title = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    y = 30
    
    # 标题
    draw.text((width//2, y), title, fill=accent_color, font=font_title, anchor="mm")
    y += 60
    
    # 项目信息
    draw.text((40, y), f"📅 项目周期：{period}", fill=text_color, font=font_text)
    y += 40
    draw.text((40, y), f"🎯 目标：{goal}", fill=text_color, font=font_text)
    y += 60
    
    # 分隔线
    draw.line([(40, y), (width-40, y)], fill=line_color, width=2)
    y += 30
    
    # 每日安排
    for day, tasks in days:
        draw.text((40, y), day, fill=accent_color, font=font_header)
        y += 40
        
        for task in tasks:
            draw.text((60, y), task, fill=text_color, font=font_text)
            y += 32
        
        y += 20
    
    # 分隔线
    draw.line([(40, y), (width-40, y)], fill=line_color, width=2)
    y += 30
    
    # 关键节点
    draw.text((40, y), "⚠️ 关键节点", fill=accent_color, font=font_header)
    y += 40
    
    for milestone in milestones:
        draw.text((60, y), milestone, fill=text_color, font=font_text)
        y += 30
    
    y += 30
    
    # 底部
    if footer:
        draw.text((width//2, y), footer, fill=(100, 100, 100), font=font_small, anchor="mm")
        y += 50
    
    # 保存图片
    output_path = "generated_schedule.png"
    img.save(output_path)
    return output_path


def create_message_image(title, content_lines, footer=""):
    """
    创建通用消息图片
    
    参数:
        title: 标题
        content_lines: 内容行列表
        footer: 底部文字
    
    返回:
        图片保存路径
    """
    width = 800
    height = 150 + len(content_lines) * 35 + 80
    
    bg_color = (255, 255, 255)
    text_color = (0, 0, 0)
    accent_color = (0, 150, 136)
    
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 32)
        font_text = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
    except:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    y = 30
    
    # 标题
    draw.text((width//2, y), title, fill=accent_color, font=font_title, anchor="mm")
    y += 60
    
    # 内容
    for line in content_lines:
        draw.text((50, y), line, fill=text_color, font=font_text)
        y += 35
    
    # 底部
    if footer:
        y += 20
        draw.text((width//2, y), footer, fill=(100, 100, 100), font=font_small, anchor="mm")
    
    output_path = "generated_message.png"
    img.save(output_path)
    return output_path


if __name__ == "__main__":
    # 测试
    print("图片生成模块")
    print("使用示例:")
    print("  from image_generator import create_schedule_image")
    print("  path = create_schedule_image(...)")
