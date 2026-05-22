# AI主动客户复盘 - 执行历史

## 2026-05-22 16:24
- **扫描**: sessionType=private 精准过滤 → 43私聊 → 排除后13个
- **目标**: Timotion standing desk factory（score=4，有意向+18天沉默，无冷却）
- **消息**: 48条历史消息，跨56天，约30轮对话（isSender标记不可靠，通过内容判断）
- **话术**: 同行交流型，提T412/T423之前聊过的型号，问项目进展
- **结果**: ✅ 发送成功
- **修复**: 
  - scan_private_chats.py 改用 sessionType="private" 过滤（之前用 @chatroom 字符串，误拉群聊）
  - get_messages limit>50时返回空，limit≤60正常（48条上限）
