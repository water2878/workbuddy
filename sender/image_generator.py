"""
长文本转图片生成器
微信消息太长时，生成图片发送避免刷屏
"""
import os
import textwrap
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from config import CACHE_DIR, log


# 默认样式
_BG_COLOR = (255, 255, 255)       # 白色背景
_TEXT_COLOR = (33, 33, 33)         # 深灰文字
_TITLE_COLOR = (0, 0, 0)          # 黑色标题
_ACCENT_COLOR = (52, 120, 246)    # 蓝色强调
_LINE_SPACING = 8
_MARGIN = 40
_LINE_HEIGHT = 28
_TITLE_HEIGHT = 42


def _get_font(size: int) -> "ImageFont":
    """获取字体，优先中文字体"""
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",     # 黑体
        "C:/Windows/Fonts/simsun.ttc",     # 宋体
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    return ImageFont.load_default()


def create_message_image(
    title: str = "",
    content_lines: list[str] = None,
    footer: str = "",
    output_path: str = None,
) -> str:
    """将文字内容生成为图片

    Args:
        title: 标题
        content_lines: 内容行列表
        footer: 底部文字
        output_path: 输出路径，不指定则自动生成

    Returns:
        生成的图片路径
    """
    if not HAS_PIL:
        raise ImportError("PIL/Pillow 未安装")

    if not content_lines:
        content_lines = []

    font = _get_font(_LINE_HEIGHT - 6)
    title_font = _get_font(_TITLE_HEIGHT - 8)
    footer_font = _get_font(18)

    # 计算画布尺寸
    max_width = 600
    wrap_width = max_width - _MARGIN * 2

    # 计算每行文本实际渲染宽度，决定是否换行
    wrapped_lines = []
    for line in content_lines:
        if not line.strip():
            wrapped_lines.append("")
            continue
        # 估算每行能容纳的字符数
        chars_per_line = max(10, wrap_width // (_LINE_HEIGHT // 2))
        if len(line) > chars_per_line:
            wrapped_lines.extend(textwrap.wrap(line, width=chars_per_line))
        else:
            wrapped_lines.append(line)

    # 画布高度
    total_height = _MARGIN  # 顶部间距
    if title:
        total_height += _TITLE_HEIGHT + _LINE_SPACING * 2
    total_height += len(wrapped_lines) * (_LINE_HEIGHT + _LINE_SPACING)
    total_height += _LINE_SPACING * 2
    if footer:
        total_height += 30 + _LINE_SPACING
    total_height += _MARGIN  # 底部间距

    total_height = max(total_height, 200)

    # 创建画布
    img = Image.new("RGB", (max_width, total_height), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 画顶部装饰线
    draw.rectangle([0, 0, max_width, 4], fill=_ACCENT_COLOR)

    y = _MARGIN

    # 标题
    if title:
        draw.text((_MARGIN, y), title, font=title_font, fill=_TITLE_COLOR)
        y += _TITLE_HEIGHT + _LINE_SPACING * 2
        # 标题下分割线
        draw.rectangle([_MARGIN, y - _LINE_SPACING, max_width - _MARGIN, y - _LINE_SPACING + 1],
                       fill=(220, 220, 220))

    # 内容
    for line in wrapped_lines:
        if line == "":
            y += _LINE_HEIGHT // 2
            continue
        draw.text((_MARGIN, y), line, font=font, fill=_TEXT_COLOR)
        y += _LINE_HEIGHT + _LINE_SPACING

    # 底部
    if footer:
        y += _LINE_SPACING * 2
        draw.rectangle([_MARGIN, y, max_width - _MARGIN, y + 1], fill=(220, 220, 220))
        y += _LINE_SPACING
        draw.text((_MARGIN, y), footer, font=footer_font, fill=(120, 120, 120))

    # 保存
    if not output_path:
        import time
        ts = int(time.time() * 1000)
        output_path = os.path.join(CACHE_DIR, f"msg_image_{ts}.png")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    log(f"[图片生成] {output_path} ({max_width}x{total_height})")

    return output_path


if __name__ == "__main__":
    # 测试
    path = create_message_image(
        title="产品报价",
        content_lines=[
            "T523 双电机升降桌",
            "尺寸：1400x700mm",
            "高度范围：710-1210mm",
            "承重：120kg",
            "",
            "价格：¥1,680/台",
            "含税含运费",
        ],
        footer="以上报价有效期3天",
    )
    print(f"生成图片: {path}")
