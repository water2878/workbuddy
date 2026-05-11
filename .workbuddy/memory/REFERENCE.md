# REFERENCE.md - 畅腾升降桌参考手册

> 本文件存放静态参考资料，不自动注入上下文。需要时主动读取。

---

## 一、完整产品知识

### 手摇款

| 型号   | 管型          | 特征                           | 基准价(元) |
| ------ | ------------- | ------------------------------ | ---------- |
| T724   | 方管 80*50mm  | 手摇无电机，正装，负载80Kg，高度710-1190mm | 335        |
| T727   | 方管 80*50mm  | 手摇矮款，正装，升降520-820mm          | 388        |
| T728   | 方管 80*50mm  | 手摇升降，正装，升降720-1200MM         | 411        |
| T729   | -             | 手摇快速版，砂黑色，升降720-1200MM       | 471        |

### 单电机款

| 型号   | 管型          | 特征                               | 基准价(元) |
| ------ | ------------- | ---------------------------------- | ---------- |
| T524   | 方管 80*50mm  | 正装，负载80Kg，2个记忆                   | 415        |
| T523   | 方管 75*45mm  | 倒装，4个记忆，儿童锁                      | 460        |
| T526   | 方管 80*50mm  | 正装，T526A                         | 543        |
| T531   | 方管 80*50mm  | 单电机L型，主台920-1400mm，副台1180-1620mm | 634        |
| T545   | 方管 80*50mm  | 单电机对向座，正装                        | 1036       |

### 双电机款

| 型号   | 管型           | 特征                          | 基准价(元) |
| ------ | -------------- | ----------------------------- | ---------- |
| T412   | 方管 80*50mm   | 正装，含线槽，4个记忆，USB，儿童锁         | 689        |
| T423   | 方管 80*50mm   | 正装，含线槽，负载120Kg，4个记忆，USB，儿童锁 | 775        |
| T621   | 椭圆管 75*45mm | 正装，椭圆形立柱，含线槽，负载120Kg        | 835        |
| T6201  | 椭圆管 75*45mm | 正装，621白色款                   | 835        |
| T435   | 方管 80*50mm   | 三脚L型，正装，90度                 | 1267       |
| T4404  | 方管 80*50mm   | 对向座双电机3节桌架                  | 1604       |

### 其他款

| 型号   | 特征           | 基准价(元) |
| ------ | -------------- | ---------- |
| F4206  | L型普通面板桌架 | 890        |

### 通用参数

- **钢架材质**: 冷轧钢
- **输入电压**: 100-240VAC
- **噪音标准**: 小于38-48分贝
- **质保**: 电动部分2年，钢架部分5年

---

## 二、技术细节

### 消息处理流程

1. WeFlow SSE 接收微信消息
2. 语音消息 → sherpa-onnx 转文字
3. 图片消息 → 识别图中升降桌特征 → 知识库比对
4. 生成回复（按李生人格）
5. 调用微信API发送回复

### 图片索引系统

- **规模**: 17个型号，151张产品图片
- **索引文件**: `core/image_indexer.py`
- **API端点**:
  - `POST /api/image/match` — 比对客户图片找型号
  - `GET /api/image/index/status` — 查看索引状态

### 微信发送模块

```python
from wechat_sender import send_text_safe, send_image_safe
send_text_safe('健康办公研究社', '消息内容')
send_image_safe('健康办公研究社', '图片路径')
```

---

## 三、客户记忆系统

### 向量记忆系统

- **文件**: `core/vector_memory.py`
- **技术栈**: BGE-M3 模型 + LanceDB
- **存储路径**: `data/vector_db/`
- **API**:
  - `POST /api/memory/store` — 存储记忆
  - `POST /api/memory/search` — 语义搜索
  - `GET /api/memory/stats` — 统计信息

### 客户画像系统

- **文件**: `core/customer_profile.py`
- **存储**: `data/chat_history/{昵称}_profile.json`
- **API**:
  - `load_profile(nickname)` - 加载画像
  - `update_profile_field(nickname, field, value)` - 更新字段
  - `add_interaction(nickname, type, content)` - 添加交互
  - `get_profile_summary(nickname)` - 获取摘要

### 客户画像自动更新

- **脚本**: `.workbuddy/automations/automation-1777517408285/update_customer_profile.py`
- **触发**: 每小时自动执行
- **功能**: 从 WeFlow API 获取对话，提取型号/价格/数量/地址/意向度

---

## 四、重要文件路径

| 用途         | 路径                                           |
| ------------ | ---------------------------------------------- |
| 产品图库     | `C:/Users/Lenovo/WorkBuddy/Claw/assets/images/` |
| 人格配置     | `C:/Users/Lenovo/WorkBuddy/Claw/personas/lisheng.md` |
| 产品目录     | `C:/Users/Lenovo/WorkBuddy/Claw/PRODUCT_CATALOG.md` |
| WeFlow缓存   | `C:/Users/Lenovo/AppData/Roaming/weflow/cache/api-media/` |
| 问答对数据   | `data/qa_pairs.json`（210万条）                  |
| 云端图片服务 | `http://120.26.84.224:5032/contracts/images/{filename}` |

---

## 五、服务端口

| 服务          | 端口   | 说明      |
| ------------- | ------ | --------- |
| Claw API      | 5032   | 主API服务器 |
| WebSocket同步 | 5033   | 云端文件同步 |
| 文件服务      | 5032   | 静态文件访问 |

---

_本文件为静态参考，按需读取。最后更新: 2026-05-08_
