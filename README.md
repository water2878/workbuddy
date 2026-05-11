# Claw — AI 驱动的微信客服工具集

## 架构

```
客户消息 → WeFlow SSE → PowerShell桥接 → WorkBuddy(AI大脑)
                                              ↓ 决策
API调用 → Python工具服务(手脚) → WeChat UI → 客户
```

**核心理念**：AI 做大脑决策，Python 只做手脚执行。

## 模块说明

| 模块 | 职责 | 端口 |
|------|------|------|
| `core/app.py` | Flask API 服务器（AI 调用入口） | 5032 |
| `core/config.py` | 统一配置 | - |
| `core/weflow_client.py` | WeFlow API 客户端 | - |
| `core/product_service.py` | 产品图片查找、选图、发图记录 | - |
| `core/customer_service.py` | 客户记忆 CRUD | - |
| `sender/wechat_sender.py` | WeChat UI 自动化发送 | - |
| `sender/image_generator.py` | 长文转图片 | - |
| `contract/` | 合同生成系统（从旧项目迁移） | - |
| `weflow-wb-bridge.ps1` | WeFlow → WorkBuddy 消息桥接 | - |

## API 接口

### 消息发送
- `POST /api/send/text` — 发送文字 `{"contact":"名字","message":"内容"}`
- `POST /api/send/image` — 发送图片 `{"contact":"名字","image_path":"路径"}` 或 `{"model":"型号"}`
- `POST /api/send/file` — 发送文件
- `POST /api/send-product-image` — 一键发产品图 `{"contact":"名字","model":"型号"}`

### 产品
- `GET /api/products` — 列出所有产品
- `GET /api/products/search?q=T523` — 搜索产品
- `GET /api/products/{model}/images` — 获取产品图片
- `GET /api/products/{model}/pick-image` — 选最佳图片
- `GET /api/products/knowledge` — 产品知识库文本

### 聊天记录
- `GET /api/chat-history/{session_id}` — 获取聊天记录
- `GET /api/contacts` — 联系人列表
- `GET /api/sessions` — 会话列表

### 客户记忆
- `GET /api/customers` — 列出客户
- `GET /api/customers/{id}` — 获取客户信息
- `POST /api/customers/{id}` — 保存客户信息
- `POST /api/customers/{id}/notes` — 更新备注
- `POST /api/customers/{id}/order` — 添加订单

### 合同
- `POST /api/contracts/generate` — 生成合同
- `GET /api/contracts` — 列出合同

### 图片
- `POST /api/text-to-image` — 文字转图片
- `GET /api/images/serve?path=xxx` — 提供图片文件

## 启动

```bash
# 1. 启动工具 API 服务器
python core/app.py

# 2. 启动 WeFlow 桥接（已独立运行）
# start-wb-bridge.bat
```

## 与旧项目的区别

| 功能 | 旧架构 | 新架构 |
|------|--------|--------|
| LLM 调用 | Python 调 Moonshot | ❌ AI 直接处理 |
| 自动回复决策 | Python 代码判断 | ❌ AI 决策 |
| 上下文管理 | context_manager.py | ❌ AI 管理 |
| Vision 索引 | 自动建索引 | ❌ AI 自己看图 |
| 语音识别 | sherpa 批量转写 | ❌ AI 处理 |
| 消息发送 | ✅ 保留 | ✅ 保留 |
| 产品图片 | ✅ 保留 | ✅ 保留 |
| 合同生成 | ✅ 保留 | ✅ 保留 |
| 客户记忆 | 向量数据库 | ✅ JSON 简化版 |
