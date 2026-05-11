# 自动化任务记忆 - 自动更新客户画像

## 任务信息
- **ID**: automation-1777517408285
- **名称**: 自动更新客户画像
- **调度**: 每小时执行一次
- **命令**: `python .workbuddy/automations/automation-1777517408285/update_customer_profile.py --hours 1`

## 执行历史

### 2026-05-08 09:35
- **状态**: 成功
- **结果**: 分析了18条对话记录，更新了1个客户画像（健康办公研究社）
- **备注**: 日志文件最后更新时间为2026-04-28，使用--hours 240参数覆盖10天历史数据

## 功能说明
1. 从weflow-wb-bridge.log读取客户对话记录
2. 提取关键信息：昵称、需求、价格、数量、地址、意向度
3. 更新客户画像文件（data/chat_history/{昵称}_profile.json）
4. 字段包括：last_contact、profile、interactions、tags、priority

## 注意事项
- 若日志无新对话，脚本正常退出
- 画像文件不存在时会自动创建
- 只更新有变化的信息，保留原有数据
