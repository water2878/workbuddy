# 微信自动化发送工具

一个简单易用的微信消息自动化发送工具，支持文字消息（分段发送）和图片发送。

## 功能特性

- ✅ **文字消息发送** - 支持单条和分段发送
- ✅ **图片发送** - 支持图片+文字说明
- ✅ **图片生成** - 自动生成格式化的消息图片
- ✅ **稳定可靠** - 点击任务栏图标激活微信

## 安装

### 1. 克隆或下载本项目

```bash
git clone <项目地址>
cd wechat-automation
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置坐标

根据你的屏幕分辨率，编辑 `config.py` 中的坐标：

```python
# 微信任务栏图标位置（右下角）
WECHAT_ICON = (1850, 1050)

# 聊天输入框位置
INPUT_BOX = (1437, 963)
```

**如何获取坐标？**
- 运行 `python get_coord.py`
- 将鼠标移到微信任务栏图标位置，记录坐标
- 将鼠标移到聊天输入框位置，记录坐标

## 快速开始

### 发送文字消息

```python
from wechat_sender import send_text, send_text_segments

# 发送单条消息
send_text("李昊", "你好，这是测试消息")

# 分段发送（推荐用于长消息）
messages = [
    "【项目汇报】",
    "",
    "一、今日完成",
    "• 功能A开发完成",
    "• 功能B测试通过",
    "",
    "二、明日计划",
    "• 继续优化性能"
]
send_text_segments("尹国锋", messages)
```

### 发送图片

```python
from wechat_sender import send_image

# 发送图片（带文字说明）
send_image("李昊", "screenshot.png", "这是截图说明")

# 仅发送图片
send_image("李昊", "screenshot.png")
```

### 生成并发送图片消息

```python
from image_generator import create_schedule_image
from wechat_sender import send_image

# 创建项目安排图片
days = [
    ("周一", ["任务1", "任务2"]),
    ("周二", ["任务3", "任务4"])
]
milestones = ["周三完成", "周四交付"]

image_path = create_schedule_image(
    title="项目时间安排",
    period="周一到周四",
    goal="完成项目开发",
    days=days,
    milestones=milestones
)

# 发送图片
send_image("尹国锋", image_path, "请查看项目安排")
```

## 完整示例

见 `examples/` 目录：
- `send_text_example.py` - 文字消息示例
- `send_image_example.py` - 图片消息示例
- `generate_schedule_example.py` - 生成项目安排图片示例

## 注意事项

1. **微信必须登录** - 确保微信PC版已登录
2. **微信窗口可见** - 微信可以最小化，但必须在任务栏
3. **坐标配置** - 首次使用需要根据屏幕分辨率配置坐标
4. **发送延迟** - 为避免被检测为机器人，发送有适当延迟

## 文件结构

```
wechat-automation/
├── README.md              # 本文件
├── requirements.txt       # 依赖列表
├── config.py             # 坐标配置
├── wechat_sender.py      # 消息发送模块
├── image_generator.py    # 图片生成模块
├── get_coord.py          # 坐标获取工具
├── examples/             # 示例代码
│   ├── send_text_example.py
│   ├── send_image_example.py
│   └── generate_schedule_example.py
└── SKILL.md              # 技能文档（内部使用）
```

## 依赖

- Python 3.8+
- pyautogui
- pyperclip
- pywinauto
- Pillow
- rapidocr_onnxruntime（可选，用于OCR）

## ⚠️ 重要说明

### 激活方式差异（关键！）

**单条消息发送**（如 `send_text("李昊", "消息")`）
- 每次都会点击任务栏图标激活微信
- 适合独立操作，确保微信窗口正确激活

**批量发送不同消息**（连续给不同人发不同内容）
- 第一次：点击任务栏激活
- 后续：使用Ctrl+F搜索新联系人（保持窗口激活）
- 避免重复点击任务栏打断当前聊天

```python
# 批量发送示例
from wechat_sender import activate_wechat, send_text

# 第一次：激活微信
activate_wechat()

# 给A发送（保持激活状态）
send_text("李昊", "消息A")

# 给B发送（直接搜索，不重新激活）
send_text("尹国锋", "消息B")
```

### 鲁棒性说明

⚠️ **当前版本的限制**：

1. **坐标依赖**：需要根据屏幕分辨率配置坐标
2. **微信位置**：微信必须在任务栏固定位置
3. **单显示器**：暂不支持多显示器环境
4. **分辨率**：推荐1920x1080分辨率

**换设备后需要**：
1. 重新运行 `python get_coord.py` 获取坐标
2. 更新 `config.py` 中的坐标配置
3. 测试发送功能是否正常

### 使用建议

- 首次使用前务必配置坐标
- 建议先给测试对象发消息验证
- 批量发送时建议添加适当延迟
- 遇到问题检查微信窗口是否被其他窗口遮挡

## 许可证

MIT License
