# 产品图片发送接口文档

> **更新时间**: 2026-04-30  
> **统一发图入口**: `/api/send-product-image`

---

## 📤 发送产品图片（统一入口）

### `POST /api/send-product-image`

一键发送产品图片（智能选图 + 发送 + 记录）

**请求参数**:
```json
{
  "contact": "联系人名称",
  "model": "产品型号",
  "session_id": "会话ID（可选，用于追踪已发图片）"
}
```

**响应**:
```json
{
  "success": true,
  "image_path": "图片绝对路径",
  "model": "T412",
  "message": "发送成功"
}
```

**使用场景**:
- 客户询问某型号时，自动发送产品图片
- 客服系统一键发图
- 合同生成时插入产品图片

---

## 🔍 获取产品图片（不发送）

### `GET /api/products/<model>/images`

获取某型号的所有图片列表

**响应**:
```json
{
  "model": "T412",
  "images": ["/path/to/1.jpg", "/path/to/2.jpg"],
  "count": 2
}
```

---

### `GET /api/products/<model>/pick-image`

智能选择最佳图片（不发送，仅返回路径）

**查询参数**:
- `session_id`: 会话ID（可选，用于防重复）

**响应**:
```json
{
  "model": "T412",
  "image": "/path/to/best.jpg"
}
```

**智能选图策略**:
1. 优先选文件名带序号（`_01`, `_02`）的
2. 优先选 `jpg/jpeg` 格式
3. 优先选文件名含 `main/整体/主图` 的
4. 避免选文件名含 `detail/parts/配件` 的细节图

---

## 📋 产品列表

### `GET /api/products`

列出所有产品型号及图片数量

**响应**:
```json
[
  {"model": "T412", "image_count": 5, "images": [...]},
  {"model": "T423", "image_count": 3, "images": [...]}
]
```

---

### `GET /api/products/search?query=T4`

搜索产品型号

**响应**:
```json
[
  {"model": "T412", "image_count": 5, "images": [...]},
  {"model": "T423", "image_count": 3, "images": [...]}
]
```

---

## 🔧 核心函数（内部使用）

### `product_service.py`

```python
# 智能选图（主要函数）
pick_best_image(model, session_id, prefer_tags, specified_index, sequential)

# 对外接口
get_next_image_for_customer(model, customer_id, request_type)
# request_type: "smart" | "next" | "index:N"

# 查找产品所有图片
find_product_images(model)

# 扫描所有产品图片
scan_product_images()

# 记录已发图片（防重复）
record_sent_image(session_id, model, image_path)

# 获取近期已发图片
get_recent_sent_paths(session_id)
```

---

## 📁 图片目录结构

```
assets/images/
├── T412/           # T412 产品图片
│   ├── T412_01.jpg
│   ├── T412_02.jpg
│   └── T412_detail.jpg
├── T423/           # T423 产品图片
│   └── ...
└── ...
```

**规则**:
- 每个型号独立目录
- 目录名 = 型号名（大写）
- 支持格式: jpg, jpeg, png, gif, bmp, webp

---

## 🎯 使用示例

### 示例1: 发送产品图片给客户
```bash
curl -X POST http://localhost:5000/api/send-product-image \
  -H "Content-Type: application/json" \
  -d '{
    "contact": "张三",
    "model": "T412",
    "session_id": "wxid_xxx"
  }'
```

### 示例2: 获取最佳图片路径
```bash
curl "http://localhost:5000/api/products/T412/pick-image?session_id=wxid_xxx"
```

### 示例3: Python 代码调用
```python
from core.product_service import get_next_image_for_customer

# 智能选图
img_path, desc = get_next_image_for_customer("T412", "customer_001", "smart")

# 顺序发下一张
img_path, desc = get_next_image_for_customer("T412", "customer_001", "next")

# 发指定序号（第1张）
img_path, desc = get_next_image_for_customer("T412", "customer_001", "index:0")
```

---

## 📝 更新日志

- **2026-04-30**: 统一发图入口为 `/api/send-product-image`
- **2026-04-30**: 删除重复的 `send_image` 接口
- **2026-04-30**: 合同生成使用智能选图
- **2026-04-30**: 删除型号目录映射，每个型号独立目录
