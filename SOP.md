# Claw 客服系统 SOP（标准操作流程）

> **版本**: 1.0  
> **更新日期**: 2026-04-29  
> **适用范围**: 畅腾升降桌客服工作

---

## 一、每日开工流程

### 1.1 启动系统
```bash
# 方式1：一键启动（推荐）
start-all.bat

# 方式2：分别启动
python weflow_wb_bridge.py    # 消息桥接
python core/app.py             # API服务
```

### 1.2 检查系统状态
- [ ] Bridge 正常连接 WeFlow
- [ ] WorkBuddy 窗口正常
- [ ] 微信客户端已登录
- [ ] API 服务端口 5032 正常

---

## 二、客户消息处理流程

### 2.1 消息接收
```
客户微信消息 → WeFlow SSE → Bridge → WorkBuddy（我收到）
```

### 2.2 消息处理原则
1. **所有消息都会转发到 WorkBuddy**
2. **Bridge 不会自动回复**（已禁用 AI 回复）
3. **需要我手动决策并回复**

### 2.3 回复方式
```bash
# 方式1：使用 send_reply.py
python send_reply.py "客户名称" "回复内容"

# 方式2：Python 命令行
python -c "
import sys
sys.path.insert(0, 'sender')
from wechat_sender import send_text_safe
result = send_text_safe('客户名称', '回复内容')
print(result)
"
```

---

## 三、产品咨询 SOP

### 3.1 客户问价格
1. 确认客户需求：
   - 桌架类型（单电机/双电机/手摇）
   - 管型偏好（方管/椭圆管）
   - 节数要求（2节/3节）
   - 数量（样品/批量）

2. 提供对应报价：
   - 参考 `PRODUCT_CATALOG.md`
   - 说明价格含税不包邮
   - 告知最小订货量（100套起批）

### 3.2 客户问型号区别
| 对比维度 | 说明要点 |
|----------|----------|
| **电机数** | 单电机性价比高，双电机更稳定 |
| **管型** | 方管经济，椭圆管美观 |
| **节数** | 2节性价比高，3节升降范围大 |
| **安装** | 正装稳定，倒装美观 |

### 3.3 客户要产品图片
```bash
# 发送特定型号图片
python -c "
import sys
sys.path.insert(0, 'sender')
from wechat_sender import send_product_image
send_product_image('客户名称', 'T412')
"
```

---

## 四、合同处理 SOP

### 4.1 生成合同流程
1. 收集客户信息：
   - 公司名称
   - 联系人/电话
   - 收货地址
   - 产品型号、数量、价格

2. 调用合同生成 API：
```bash
curl -X POST http://127.0.0.1:5032/api/contracts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "客户名称",
    "contact": "联系人",
    "phone": "电话",
    "address": "地址",
    "items": [
      {"model": "T412", "quantity": 10, "price": 750}
    ],
    "sales_id": "lisheng"
  }'
```

3. 合同生成后：
   - 发送给客户确认
   - 客户确认后推送云端审批
   - 审批通过后自动下载 PDF
   - 发送 PDF 给客户

### 4.2 合同状态跟踪
| 状态 | 操作 |
|------|------|
| 待审批 | 等待云端审批 |
| 已通过 | 下载 PDF 发送客户 |
| 已拒绝 | 联系客户修改 |

---

## 五、客户画像维护 SOP

### 5.1 新建客户画像
当有新客户咨询时，创建画像文件：
`data/chat_history/{客户昵称}_profile.json`

### 5.2 更新时机
- 首次咨询后 → 创建基础画像
- 每次对话后 → 更新互动记录
- 下单后 → 更新订单信息
- 成交后 → 更新标签和优先级

### 5.3 关键信息记录
```json
{
  "customer_type": "B端/C端",
  "industry": "行业",
  "demand_type": "批发/定制/零售",
  "quantity": "数量需求",
  "budget": "预算范围",
  "pain_points": "痛点",
  "tags": ["高意向", "定制需求"],
  "priority": "高/中/低"
}
```

---

## 六、常见问题处理

### 6.1 客户说价格贵
1. 强调产品质量（冷轧钢、2-5年质保）
2. 说明批量优惠（200套/400套阶梯价）
3. 对比竞品优势（噪音小、功能全）

### 6.2 客户要定制
1. 确认定制内容：
   - 颜色（常规：黑/白/银灰）
   - 管型（方管/椭圆管/圆管）
   - 特殊功能（USB、儿童锁等）

2. 评估可行性：
   - 查询是否有现成模具
   - 评估起订量（通常100套起）
   - 确认交期（2-3周起）

### 6.3 客户问售后
- 电动部分：2年质保
- 钢架部分：5年质保
- 非人为因素免费维修

---

## 七、系统故障处理

### 7.1 Bridge 断开连接
```bash
# 1. 检查 WeFlow 是否运行
# 2. 重启 Bridge
python weflow_wb_bridge.py
```

### 7.2 微信发送失败
1. 检查微信窗口是否在前台
2. 检查输入框坐标是否正确
3. 重启微信客户端

### 7.3 API 服务无响应
```bash
# 检查端口占用
netstat -ano | findstr 5032

# 重启 API 服务
python core/app.py
```

---

## 八、工作记录要求

### 8.1 每日记录
- 客户咨询数量
- 成交订单数量
- 合同生成数量

### 8.2 客户跟进
- 高意向客户每日跟进
- 待审批合同及时催促
- 已成交客户定期回访

---

## 九、重要联系方式

| 项目 | 信息 |
|------|------|
| **公司** | 佛山畅腾智能家居有限公司 |
| **联系人** | 梁惠心 |
| **手机** | +86 18029230936 |
| **电话** | +86-757-6325 8283 |
| **邮箱** | sales03@gdhsmart.com |
| **网址** | www.ctuser.com |

---

## 十、附录

### 10.1 快速参考
- 产品报价：`PRODUCT_CATALOG.md`
- 客户画像：`data/chat_history/`
- 合同文件：`data/contracts/`
- 系统日志：`logs/`

### 10.2 常用命令
```bash
# 启动系统
start-all.bat

# 发送消息
python send_reply.py "客户" "内容"

# 查看合同
ls data/contracts/pending/
```

---

*本文档由 AI 助手维护，如有更新请及时同步。*
