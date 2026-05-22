"""
WeFlow API 客户端
严格遵循 docs/HTTP-API.md 和 docs/WeFlow消息推送服务说明.md 实现
"""

import requests
import json
from typing import Optional, Iterator
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WeFlowMessage:
    """SSE推送消息结构 - 严格遵循文档"""
    event: str                    # 固定为 "message.new"
    session_id: str               # 会话ID (群聊: xxx@chatroom, 私聊: wxid_xxx)
    message_key: str              # 消息唯一标识（用于去重）
    avatar_url: Optional[str]     # 头像URL
    source_name: str              # 发送者名称
    group_name: Optional[str]     # 群聊名称（仅群聊有）
    content: str                  # 消息内容
    
    # 扩展字段（从session_id推断）
    is_group: bool = False

    # 多媒体字段（SSE不推送，需通过API补全）
    local_type: Optional[int] = None    # 消息类型：1文本/3图片/34语音/43视频/47表情/42名片/48位置/49链接文件
    media_type: Optional[str] = None    # 媒体类型：image/voice/video/emoji
    media_url: Optional[str] = None     # 媒体HTTP地址
    media_local_path: Optional[str] = None  # 媒体本地路径
    
    def __post_init__(self):
        # 防御性处理：确保 session_id 是字符串
        if self.session_id is None:
            self.session_id = ""
        self.is_group = "@chatroom" in self.session_id
        # 从 content 推断 local_type（SSE推送时）
        if self.local_type is None and self.content:
            self.local_type = self._infer_type_from_content(self.content)
    
    @staticmethod
    def _infer_type_from_content(content: str) -> int:
        """从content文本推断消息类型（SSE不推送localType时的降级方案）"""
        if content is None:
            return 1  # 默认文本类型
        content_stripped = content.strip()
        type_map = {
            "[图片]": 3, "[语音]": 34, "[语音消息]": 34,
            "[视频]": 43, "[表情]": 47, "[名片]": 42,
            "[位置]": 48, "[链接]": 49, "[文件]": 49,
        }
        return type_map.get(content_stripped, 1)  # 默认文本
    
    @property
    def is_multimedia(self) -> bool:
        """是否为多媒体消息（图片/语音/视频/表情）"""
        return self.local_type in (3, 34, 43, 47)
    
    @property
    def is_image(self) -> bool:
        return self.local_type == 3
    
    @property
    def is_voice(self) -> bool:
        return self.local_type == 34
    
    @property
    def is_video(self) -> bool:
        return self.local_type == 43
    
    @classmethod
    def from_sse_data(cls, data: dict) -> "WeFlowMessage":
        """从SSE数据解析消息"""
        # 注意：SSE推送可能带localType字段（多媒体类型），必须读取
        return cls(
            event=data.get("event", "message.new"),
            session_id=data.get("sessionId", ""),
            message_key=data.get("messageKey", ""),
            avatar_url=data.get("avatarUrl"),
            source_name=data.get("sourceName", ""),
            group_name=data.get("groupName"),
            content=data.get("content", ""),
            local_type=data.get("localType"),  # 关键：读取多媒体类型
        )
    
    @classmethod
    def from_api_message(cls, msg_data: dict, session_id: str = "") -> "WeFlowMessage":
        """从API返回的消息数据构建（含完整多媒体字段）"""
        return cls(
            event="message.new",
            session_id=session_id or msg_data.get("senderUsername", ""),
            message_key=f"api:{msg_data.get('serverId', '')}:{msg_data.get('localId', '')}",
            avatar_url=None,
            source_name=msg_data.get("senderUsername", ""),
            group_name=None,
            content=msg_data.get("content", ""),
            local_type=msg_data.get("localType"),
            media_type=msg_data.get("mediaType"),
            media_url=msg_data.get("mediaUrl"),
            media_local_path=msg_data.get("mediaLocalPath"),
        )
    
    def enrich_from_api(self, msg_data: dict):
        """用API返回的消息数据补全多媒体字段"""
        self.local_type = msg_data.get("localType", self.local_type)
        self.media_type = msg_data.get("mediaType", self.media_type)
        self.media_url = msg_data.get("mediaUrl", self.media_url)
        self.media_local_path = msg_data.get("mediaLocalPath", self.media_local_path)
    
    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "sessionId": self.session_id,
            "messageKey": self.message_key,
            "avatarUrl": self.avatar_url,
            "sourceName": self.source_name,
            "groupName": self.group_name,
            "content": self.content,
            "localType": self.local_type,
            "mediaType": self.media_type,
            "mediaUrl": self.media_url,
            "mediaLocalPath": self.media_local_path,
        }


class WeFlowClient:
    """WeFlow HTTP API 客户端"""
    
    # 消息类型映射（来自文档）
    MSG_TYPES = {
        1: "文本",
        3: "图片",
        34: "语音",
        43: "视频",
        47: "表情",
        42: "名片",
        48: "位置",
        49: "链接/文件",
    }
    
    def __init__(self, base_url: str = "http://127.0.0.1:5031", token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self.params_auth = {"access_token": token}
    
    def _get(self, endpoint: str, params: dict = None) -> dict:
        """GET请求"""
        url = f"{self.base_url}{endpoint}"
        params = {**(params or {}), **self.params_auth}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    
    def _post(self, endpoint: str, data: dict = None) -> dict:
        """POST请求"""
        url = f"{self.base_url}{endpoint}"
        headers = {**self.headers, "Content-Type": "application/json"}
        resp = requests.post(
            url, 
            headers=headers, 
            json={**(data or {}), "access_token": self.token},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    
    def health_check(self) -> dict:
        """健康检查"""
        return self._get("/health")
    
    def get_messages(
        self, 
        talker: str, 
        limit: int = 100,
        offset: int = 0,
        start: str = None,
        end: str = None,
        keyword: str = None,
        chatlab: bool = False,
        media: bool = False
    ) -> dict:
        """
        获取消息
        
        Args:
            talker: 会话ID (wxid_xxx 或 xxx@chatroom)
            limit: 返回条数 (1-10000)
            offset: 分页偏移
            start: 开始时间 (YYYYMMDD或时间戳)
            end: 结束时间
            keyword: 关键词过滤
            chatlab: 是否返回ChatLab格式
            media: 是否导出媒体
        """
        params = {
            "talker": talker,
            "limit": limit,
            "offset": offset,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if keyword:
            params["keyword"] = keyword
        if chatlab:
            params["chatlab"] = "1"
        if media:
            params["media"] = "1"
        
        return self._get("/api/v1/messages", params)
    
    def get_sessions(self, keyword: str = None, limit: int = 100) -> dict:
        """获取会话列表"""
        params = {"limit": limit}
        if keyword:
            params["keyword"] = keyword
        return self._get("/api/v1/sessions", params)
    
    def get_contacts(self, keyword: str = None, limit: int = 100) -> dict:
        """获取联系人列表"""
        params = {"limit": limit}
        if keyword:
            params["keyword"] = keyword
        return self._get("/api/v1/contacts", params)
    
    def get_group_members(
        self, 
        chatroom_id: str,
        include_message_counts: bool = False,
        force_refresh: bool = False
    ) -> dict:
        """获取群成员列表"""
        params = {"chatroomId": chatroom_id}
        if include_message_counts:
            params["includeMessageCounts"] = "1"
        if force_refresh:
            params["forceRefresh"] = "1"
        return self._get("/api/v1/group-members", params)
    
    def listen_sse(self) -> Iterator[WeFlowMessage]:
        """
        SSE长连接监听新消息
        
        Yields:
            WeFlowMessage: 新消息对象
        """
        url = f"{self.base_url}/api/v1/push/messages"
        
        resp = requests.get(
            url,
            headers=self.headers,
            params=self.params_auth,
            stream=True,
            timeout=(10, None),  # 连接超时10s，读取不限时
        )
        resp.raise_for_status()
        
        current_event = ""
        current_data = ""
        
        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue
                
            if not line:
                # 空行表示事件结束
                if current_event and current_data:
                    if current_event == "message.new":
                        try:
                            data = json.loads(current_data)
                            if data and isinstance(data, dict):
                                msg = WeFlowMessage.from_sse_data(data)
                                if msg and msg.message_key:  # 确保消息有效
                                    yield msg
                        except (json.JSONDecodeError, TypeError, AttributeError) as e:
                            # 忽略解析错误，继续监听
                            pass
                current_event = ""
                current_data = ""
                continue
            
            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                current_data = line[5:].strip()
    
    @staticmethod
    def get_msg_type_name(local_type: int) -> str:
        """获取消息类型名称"""
        return WeFlowClient.MSG_TYPES.get(local_type, f"未知类型({local_type})")
    
    def enrich_message_media(self, msg: WeFlowMessage) -> bool:
        """
        通过API补全消息的多媒体字段。
        SSE推送不含localType/mediaUrl等字段，需要调API获取。
        
        Returns:
            True 表示补全成功
        """
        try:
            data = self.get_messages(
                talker=msg.session_id,
                limit=10,  # 增加获取的消息数量，提高匹配几率
                media=True,
            )
            messages = data.get("messages", [])
            
            # 方式1：通过 content 精确匹配（SSE的content就是API的content）
            for m in messages:
                if m.get("content") == msg.content:
                    msg.enrich_from_api(m)
                    return True
            
            # 方式2：如果是图片消息，特殊处理
            if msg.is_image or msg.content.strip() == "[图片]":
                for m in messages:
                    if m.get("localType") == 3:  # 3表示图片
                        msg.enrich_from_api(m)
                        return True
            
            # 方式3：如果是语音消息，特殊处理
            elif msg.is_voice or msg.content.strip() == "[语音]":
                for m in messages:
                    if m.get("localType") == 34:  # 34表示语音
                        msg.enrich_from_api(m)
                        return True
            
            # 方式4：如果是视频消息，特殊处理
            elif msg.is_video or msg.content.strip() == "[视频]":
                for m in messages:
                    if m.get("localType") == 43:  # 43表示视频
                        msg.enrich_from_api(m)
                        return True
            
            # 方式5：通过 localType 匹配
            if msg.local_type:
                for m in messages:
                    if m.get("localType") == msg.local_type:
                        msg.enrich_from_api(m)
                        return True
            
            # 方式6：尝试匹配最近的多媒体消息
            for m in messages:
                if m.get("localType") in (3, 34, 43, 47):  # 多媒体类型
                    msg.enrich_from_api(m)
                    return True
            
            return False
        except Exception as e:
            import traceback
            print(f"[enrich_message_media] 异常: {e}")
            print(traceback.format_exc())
            return False
    
    def get_messages_chatlab(
        self,
        talker: str,
        limit: int = None,
        offset: int = 0,
        since: int = None,
        end: int = None,
    ) -> dict:
        """
        获取消息（ChatLab格式，比 /api/v1/messages 更可靠）
        注意: 不要传 limit 参数，否则可能返回空（API bug）
        
        Args:
            talker: 会话ID (wxid_xxx 或 xxx@chatroom)
            limit: 返回条数（慎用，可能导致空结果）
            offset: 分页偏移
            since: 增量拉取的起始时间戳（秒）
            end: 时间上界
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if since:
            params["since"] = since
        if end:
            params["end"] = end
        
        return self._get(f"/api/v1/sessions/{talker}/messages", params)
    
    def download_media(self, media_url: str, save_path: str = None) -> Optional[str]:
        """
        下载媒体文件到本地
        
        Args:
            media_url: 媒体HTTP地址（如 http://127.0.0.1:5031/api/v1/media/...）
            save_path: 保存路径，不指定则用临时文件
            
        Returns:
            下载后的本地文件路径，失败返回 None
        """
        import tempfile
        import os
        
        try:
            if not media_url:
                return None
            
            # 如果是本地路径且已存在，直接返回
            if save_path and os.path.isfile(save_path):
                return save_path
            
            # 通过HTTP下载
            resp = requests.get(
                media_url,
                params=self.params_auth,
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            
            if not save_path:
                # 从URL推断扩展名
                ext = os.path.splitext(media_url.split("?")[0])[1] or ".bin"
                fd, save_path = tempfile.mkstemp(suffix=ext, prefix="weflow_media_")
                os.close(fd)
            
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(resp.content)
            
            return save_path
        except Exception:
            return None
