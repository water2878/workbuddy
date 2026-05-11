# Claw 客服消息流程

## 当前工作模式（已固化）

```
客户微信消息
    ↓
WeFlow SSE 推送
    ↓
桥接脚本 (weflow_wb_bridge.py) - 纯转发模式
    ↓
WorkBuddy (我收到消息)
    ↓
我生成回复
    ↓
我调用 wechat_sender 发送给客户
```

## 配置确认

### 1. 桥接脚本配置
**文件**: `weflow_wb_bridge.py`
```python
ENABLE_AI_REPLY = False  # 纯转发，不自动回复
```

### 2. 微信发送配置
**文件**: `sender/wechat_sender.py`
```python
INPUT_BOX = (1437, 963)  # 微信输入框坐标（不要改动）
```

## 发送消息方法

当我需要回复客户时，执行以下命令：

```bash
cd c:\Users\Lenovo\WorkBuddy\Claw
python -c "
import sys
sys.path.insert(0, 'sender')
from wechat_sender import send_text_safe

message = '回复内容'
result = send_text_safe('客户名称', message)
print('发送结果:', result)
"
```

## 启动命令

### 启动桥接脚本（需要一直运行）
```bash
cd c:\Users\Lenovo\WorkBuddy\Claw
python weflow_wb_bridge.py
```

### 启动 API 服务（端口 5032）
```bash
cd c:\Users\Lenovo\WorkBuddy\Claw\core
python app.py
```

## 注意事项

1. **不要修改** `wechat_sender.py` 中的 `INPUT_BOX` 坐标
2. **不要启用** `weflow_wb_bridge.py` 中的 `ENABLE_AI_REPLY`
3. 所有客户消息都会转发到 WorkBuddy，由我决定如何回复
4. 回复需要我主动调用发送命令

## 测试状态

- ✅ 文字消息转发正常
- ✅ 图片消息转发正常
- ✅ 微信发送功能正常
- ⏳ 需要启动桥接脚本才能接收消息
