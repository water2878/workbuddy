# AI主动客户复盘 - 执行历史

## 2026-05-22 17:19
- **扫描**: 43私聊 → 排除后10个（比上次少3个，因proactive_log有5人今天已联系过在冷却期）
- **目标**: AiLy李15502540306（score=4，有意向+14天，无冷却，第一候选即命中）
- **消息**: ChatLab格式711条（普通API返回0条），最近消息为技术讨论，但之前有60-70套办公桌询价
- **话术**: 询过价型，提F4200/T412+六七十台+问考虑怎样
- **结果**: ✅ 发送成功
- **遍历**: 只需1个候选即找到切入点，跳过5个冷却期客户
- **教训**: get_messages(talker, limit=60)返回0条时用ChatLab格式(get_messages_chatlab)替代

## 2026-05-22 16:24
- **扫描**: sessionType=private 精准过滤 → 43私聊 → 排除后13个
- **目标**: Timotion standing desk factory（score=4，有意向+18天沉默，无冷却）
- **消息**: 48条历史消息，跨56天，约30轮对话（isSender标记不可靠，通过内容判断）
- **话术**: 同行交流型，提T412/T423之前聊过的型号，问项目进展
- **结果**: ✅ 发送成功
- **修复**: 
  - scan_private_chats.py 改用 sessionType="private" 过滤（之前用 @chatroom 字符串，误拉群聊）
  - get_messages limit>50时返回空，limit≤60正常（48条上限）
