# Claw API 调用指南

## 基础信息
- **Base URL**: `http://127.0.0.1:5032`
- **Content-Type**: `application/json`

---

## 1. 消息发送 API

### 发送文字消息
```bash
POST /api/send/text
{
  "contact": "健康办公研究社",
  "message": "你好！"
}
```

### 发送文件
```bash
POST /api/send/file
{
  "contact": "健康办公研究社",
  "file_path": "C:/path/to/file.pdf",
  "message": "合同文件"
}
```

---

## 2. 产品图片 API

### 列出所有产品
```bash
GET /api/products
```

### 搜索产品
```bash
GET /api/products/search?q=T524
```

### 获取产品图片列表
```bash
GET /api/products/T524/images
```

### 智能挑选最佳图片
```bash
GET /api/products/T524/pick-image?session_id=健康办公研究社
```

### 获取产品知识库
```bash
GET /api/products/knowledge
```

---

## 3. 图片识别 API

### 构建图片索引
```bash
POST /api/image/index
{
  "force": false
}
```

### 比对客户图片
```bash
POST /api/image/match
{
  "image_path": "C:/path/to/customer_image.jpg"
}
```

### 获取索引状态
```bash
GET /api/image/index/status
```

### 获取图片文件
```bash
GET /api/images/serve?path=C:/path/to/image.jpg
```

---

## 4. 语音识别 API

### 语音转文字
```bash
POST /api/transcribe
{
  "voice_path": "C:/path/to/voice.silk"
}
```

### 获取最新语音
```bash
GET /api/latest-voice?contact=健康办公研究社
```

---

## 5. 聊天记录 API

### 获取聊天记录
```bash
GET /api/chat-history/{session_id}?limit=50&keyword=价格
```

### 获取最新图片
```bash
GET /api/latest-image?contact=健康办公研究社
```

---

## 6. 客户管理 API

### 列出所有客户
```bash
GET /api/customers
```

### 获取客户详情
```bash
GET /api/customers/健康办公研究社
```

### 保存客户信息
```bash
POST /api/customers/健康办公研究社
{
  "notes": "高意向客户",
  "tags": ["B端", "写字楼"]
}
```

### 更新客户备注
```bash
POST /api/customers/健康办公研究社/notes
{
  "notes": "已报价500套T524"
}
```

### 添加客户订单
```bash
POST /api/customers/健康办公研究社/order
{
  "model": "T524",
  "quantity": 500,
  "price": 390
}
```

### 更新客户联系时间
```bash
POST /api/customers/健康办公研究社/touch
```

---

## 7. 联系人/会话 API

### 获取联系人列表
```bash
GET /api/contacts?keyword=健康&limit=20
```

### 获取会话列表
```bash
GET /api/sessions?keyword=健康&limit=20
```

---

## 8. AI 回复 API

### 获取 AI 回复
```bash
POST /api/chat/reply
{
  "contact": "健康办公研究社",
  "message": "多少钱？",
  "is_image": false,
  "voice_path": "",
  "image_path": ""
}
```

---

## 智能体调用示例

### Python 直接调用
```python
import requests

# 发送消息
response = requests.post("http://127.0.0.1:5032/api/send/text", json={
    "contact": "健康办公研究社",
    "message": "你好！"
})
print(response.json())

# 获取产品图片
response = requests.get("http://127.0.0.1:5032/api/products/T524/images")
images = response.json()["images"]

# 智能选图
response = requests.get("http://127.0.0.1:5032/api/products/T524/pick-image?session_id=健康办公研究社")
best_image = response.json()["image"]
```

### 命令行调用
```bash
# 使用 curl
curl -X POST http://127.0.0.1:5032/api/send/text \
  -H "Content-Type: application/json" \
  -d '{"contact":"健康办公研究社","message":"你好"}'
```

---

## 错误处理

所有 API 返回格式：
```json
{
  "success": true/false,
  "error": "错误信息",
  "...": "其他数据"
}
```

HTTP 状态码：
- 200: 成功
- 400: 参数错误
- 404: 资源不存在
- 500: 服务器错误
