"""
events.py — OneBot 11 事件模型
==========================================
定义所有事件类型对应的 dataclass，支持从原始字典自动分发构造。
事件分为五大类：
  1. MessageEvent    — 消息事件（群消息/私聊）
  2. NoticeEvent     — 通知事件（群变动/撤回/禁言等）
  3. RequestEvent    — 请求事件（加好友/加群）
  4. MetaEvent       — 元事件（心跳/生命周期）
  5. UnknownEvent    — 未知事件兜底
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Dict, List, Optional

# ═══════════════════════════════════════════════════════════
# 基础类型
# ═══════════════════════════════════════════════════════════


@dataclass
class Sender:
    """消息发送者信息。"""

    user_id: int = 0
    nickname: str = ""
    sex: str = "unknown"
    age: int = 0
    card: str = ""  # 群名片
    role: str = "member"  # owner/admin/member
    title: str = ""  # 群头衔

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sender":
        return cls(
            user_id=int(data.get("user_id", 0)),
            nickname=str(data.get("nickname", "")),
            sex=str(data.get("sex", "unknown")),
            age=int(data.get("age", 0)),
            card=str(data.get("card", "")),
            role=str(data.get("role", "member")),
            title=str(data.get("title", "")),
        )


@dataclass
class Anonymous:
    """匿名信息。"""

    id: int = 0
    name: str = ""
    flag: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Anonymous":
        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name", "")),
            flag=str(data.get("flag", "")),
        )


# ═══════════════════════════════════════════════════════════
# 消息段（MessageSegment）
# ═══════════════════════════════════════════════════════════


@dataclass
class MessageSegment:
    """单条消息段。"""

    type: str
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageSegment":
        return cls(type=str(data.get("type", "")), data=dict(data.get("data", {})))

    def get_text(self) -> str:
        """如果是文本段则返回文本，否则返回空。"""
        if self.type == "text":
            return str(self.data.get("text", ""))
        return ""


def parse_message(raw: Any) -> List[MessageSegment]:
    """
    将原始 message 字段解析为 MessageSegment 列表。
    支持 array 格式（消息段）和 string 格式（CQ 码）。
    """
    if isinstance(raw, str):
        # CQ 码字符串 → 简单包装为 text 段
        return [MessageSegment(type="text", data={"text": raw})]
    if isinstance(raw, list):
        result = []
        for item in raw:
            if isinstance(item, dict):
                result.append(MessageSegment.from_dict(item))
        return result
    return []


# ═══════════════════════════════════════════════════════════
# 事件基类
# ═══════════════════════════════════════════════════════════


@dataclass
class BaseEvent:
    """
    所有事件的基类。
    提供通用的 time / self_id / post_type 字段和工具方法。
    """

    time: int = 0
    self_id: int = 0
    post_type: str = ""

    # 注册表：post_type → 具体事件类
    _registry: ClassVar[Dict[str, type]] = {}

    def __init_subclass__(cls, **kwargs):
        """子类注册钩子。"""
        super().__init_subclass__(**kwargs)

    @classmethod
    def register(cls, post_type: str):
        """装饰器：将子类注册到事件分发器。"""

        def wrapper(event_cls: type) -> type:
            BaseEvent._registry[post_type] = event_cls
            return event_cls

        return wrapper

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseEvent":
        """
        工厂方法：根据 post_type 自动分发到对应子类。
        未知类型返回 UnknownEvent。
        """
        post_type = str(data.get("post_type", ""))
        event_cls = BaseEvent._registry.get(post_type)
        if event_cls is None:
            return UnknownEvent.from_dict(data)
        try:
            return event_cls.from_dict(data)
        except Exception:
            return UnknownEvent.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """将事件序列化回字典。"""
        result: Dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, list):
                result[f.name] = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
            elif hasattr(value, "to_dict"):
                result[f.name] = value.to_dict()
            else:
                result[f.name] = value
        return result

    def get_message_text(self) -> str:
        """获取事件中的纯文本（仅消息事件有效）。"""
        return ""


# ═══════════════════════════════════════════════════════════
# 消息事件
# ═══════════════════════════════════════════════════════════


@dataclass
class MessageEvent(BaseEvent):
    """消息事件基类（群消息/私聊共用字段）。"""

    message_type: str = ""
    sub_type: str = ""
    message_id: int = 0
    user_id: int = 0
    message: List[MessageSegment] = field(default_factory=list)
    raw_message: str = ""
    font: int = 0
    sender: Sender = field(default_factory=Sender)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageEvent":
        # 根据 message_type 决定具体子类
        msg_type = str(data.get("message_type", ""))
        if msg_type == "group":
            return GroupMessageEvent._from_base(data)
        elif msg_type == "private":
            return PrivateMessageEvent._from_base(data)
        # 兜底
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type=str(data.get("post_type", "message")),
            message_type=msg_type,
            sub_type=str(data.get("sub_type", "")),
            message_id=int(data.get("message_id", 0)),
            user_id=int(data.get("user_id", 0)),
            message=parse_message(data.get("message", [])),
            raw_message=str(data.get("raw_message", "")),
            font=int(data.get("font", 0)),
            sender=Sender.from_dict(data.get("sender", {})),
        )

    def get_message_text(self) -> str:
        return "".join(seg.get_text() for seg in self.message)


@dataclass
class GroupMessageEvent(MessageEvent):
    """群消息事件。"""

    group_id: int = 0
    anonymous: Optional[Anonymous] = None

    @classmethod
    def _from_base(cls, data: Dict[str, Any]) -> "GroupMessageEvent":
        anon_raw = data.get("anonymous")
        anon = Anonymous.from_dict(anon_raw) if anon_raw else None
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="message",
            message_type="group",
            sub_type=str(data.get("sub_type", "")),
            message_id=int(data.get("message_id", 0)),
            user_id=int(data.get("user_id", 0)),
            message=parse_message(data.get("message", [])),
            raw_message=str(data.get("raw_message", "")),
            font=int(data.get("font", 0)),
            sender=Sender.from_dict(data.get("sender", {})),
            group_id=int(data.get("group_id", 0)),
            anonymous=anon,
        )


@dataclass
class PrivateMessageEvent(MessageEvent):
    """私聊消息事件。"""

    target_id: int = 0  # 对端 QQ 号

    @classmethod
    def _from_base(cls, data: Dict[str, Any]) -> "PrivateMessageEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="message",
            message_type="private",
            sub_type=str(data.get("sub_type", "")),
            message_id=int(data.get("message_id", 0)),
            user_id=int(data.get("user_id", 0)),
            message=parse_message(data.get("message", [])),
            raw_message=str(data.get("raw_message", "")),
            font=int(data.get("font", 0)),
            sender=Sender.from_dict(data.get("sender", {})),
            target_id=int(data.get("target_id", data.get("user_id", 0))),
        )


# ═══════════════════════════════════════════════════════════
# 通知事件
# ═══════════════════════════════════════════════════════════


@dataclass
class NoticeEvent(BaseEvent):
    """通知事件基类。"""

    notice_type: str = ""
    group_id: int = 0
    user_id: int = 0
    operator_id: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NoticeEvent":
        ntype = str(data.get("notice_type", ""))
        # 群相关通知
        if ntype in (
            "group_ban",
            "group_kick",
            "group_admin",
            "group_decrease",
            "group_increase",
            "group_recall",
            "group_card",
            "group_title",
            "group_whole_ban",
        ):
            return GroupNoticeEvent._from_data(data)
        # 好友相关
        if ntype in ("friend_add", "friend_recall"):
            return FriendNoticeEvent._from_data(data)
        # 通知事件通用
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="notice",
            notice_type=ntype,
            group_id=int(data.get("group_id", 0)),
            user_id=int(data.get("user_id", 0)),
            operator_id=int(data.get("operator_id", 0)),
        )


@dataclass
class GroupNoticeEvent(NoticeEvent):
    """群通知事件（禁言/踢人/退群/入群/撤回等）。"""

    duration: int = 0  # 禁言时长（秒）
    sub_type: str = ""  # 子类型（leave/kick/ban/unban 等）
    target_id: int = 0  # 目标用户
    message_id: int = 0  # 撤回消息 ID

    @classmethod
    def _from_data(cls, data: Dict[str, Any]) -> "GroupNoticeEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="notice",
            notice_type=str(data.get("notice_type", "")),
            group_id=int(data.get("group_id", 0)),
            user_id=int(data.get("user_id", 0)),
            operator_id=int(data.get("operator_id", 0)),
            duration=int(data.get("duration", 0)),
            sub_type=str(data.get("sub_type", "")),
            target_id=int(data.get("target_id", data.get("user_id", 0))),
            message_id=int(data.get("message_id", 0)),
        )


@dataclass
class FriendNoticeEvent(NoticeEvent):
    """好友通知事件。"""

    @classmethod
    def _from_data(cls, data: Dict[str, Any]) -> "FriendNoticeEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="notice",
            notice_type=str(data.get("notice_type", "")),
            user_id=int(data.get("user_id", 0)),
        )


# ═══════════════════════════════════════════════════════════
# 请求事件
# ═══════════════════════════════════════════════════════════


@dataclass
class RequestEvent(BaseEvent):
    """请求事件基类（加好友/加群）。"""

    request_type: str = ""
    user_id: int = 0
    comment: str = ""
    flag: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RequestEvent":
        rtype = str(data.get("request_type", ""))
        if rtype == "group":
            return GroupRequestEvent._from_data(data)
        elif rtype == "friend":
            return FriendRequestEvent._from_data(data)
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="request",
            request_type=rtype,
            user_id=int(data.get("user_id", 0)),
            comment=str(data.get("comment", "")),
            flag=str(data.get("flag", "")),
        )


@dataclass
class GroupRequestEvent(RequestEvent):
    """加群请求。"""

    group_id: int = 0
    sub_type: str = ""  # add/invite

    @classmethod
    def _from_data(cls, data: Dict[str, Any]) -> "GroupRequestEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="request",
            request_type="group",
            user_id=int(data.get("user_id", 0)),
            comment=str(data.get("comment", "")),
            flag=str(data.get("flag", "")),
            group_id=int(data.get("group_id", 0)),
            sub_type=str(data.get("sub_type", "")),
        )


@dataclass
class FriendRequestEvent(RequestEvent):
    """加好友请求。"""

    @classmethod
    def _from_data(cls, data: Dict[str, Any]) -> "FriendRequestEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="request",
            request_type="friend",
            user_id=int(data.get("user_id", 0)),
            comment=str(data.get("comment", "")),
            flag=str(data.get("flag", "")),
        )


# ═══════════════════════════════════════════════════════════
# 元事件
# ═══════════════════════════════════════════════════════════


@dataclass
class MetaEvent(BaseEvent):
    """元事件（心跳/生命周期）。"""

    meta_event_type: str = ""
    status: Dict[str, Any] = field(default_factory=dict)
    interval: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetaEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type="meta_event",
            meta_event_type=str(data.get("meta_event_type", "")),
            status=dict(data.get("status", {})),
            interval=int(data.get("interval", 0)),
        )


# ═══════════════════════════════════════════════════════════
# 未知事件兜底
# ═══════════════════════════════════════════════════════════


@dataclass
class UnknownEvent(BaseEvent):
    """无法识别的事件，保留原始数据。"""

    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnknownEvent":
        return cls(
            time=int(data.get("time", 0)),
            self_id=int(data.get("self_id", 0)),
            post_type=str(data.get("post_type", "unknown")),
            raw=dict(data),
        )


# ═══════════════════════════════════════════════════════════
# 注册所有事件类型到分发器
# ═══════════════════════════════════════════════════════════

# 使用装饰器注册
BaseEvent.register("message")(MessageEvent)
BaseEvent.register("notice")(NoticeEvent)
BaseEvent.register("request")(RequestEvent)
BaseEvent.register("meta_event")(MetaEvent)
