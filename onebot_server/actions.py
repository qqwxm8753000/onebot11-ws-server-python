"""
actions.py — OneBot 11 Action（API 调用）模型
==========================================
每个 Action 对应一个 OneBot API，如 send_group_msg、get_login_info 等。
通过 BaseAction 基类统一序列化，通过 ActionResponse 解析回包。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Dict, List, Optional, Type, Union

# ═══════════════════════════════════════════════════════════
# 消息段构造工具
# ═══════════════════════════════════════════════════════════


def text_segment(text: str) -> Dict[str, Any]:
    """构造文本消息段。"""
    return {"type": "text", "data": {"text": text}}


def image_segment(file: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    构造图片消息段。
    file 可以是 URL、base64://... 或本地路径。
    """
    data: Dict[str, str] = {"file": file}
    if url:
        data["url"] = url
    return {"type": "image", "data": data}


def at_segment(qq: Union[int, str]) -> Dict[str, Any]:
    """构造 @某人 消息段。qq="all" 表示 @全体成员。"""
    return {"type": "at", "data": {"qq": str(qq)}}


def face_segment(id: int) -> Dict[str, Any]:
    """构造 QQ 表情消息段。id 为 QQ 表情 ID。"""
    return {"type": "face", "data": {"id": str(id)}}


def reply_segment(message_id: int) -> Dict[str, Any]:
    """构造回复消息段（引用某条消息）。"""
    return {"type": "reply", "data": {"id": str(message_id)}}


def build_message(*segments: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    将多个消息段组装为消息数组。
    用法: build_message(at_segment(123), text_segment("你好"))
    """
    return list(segments)


# ═══════════════════════════════════════════════════════════
# Action 基类
# ═══════════════════════════════════════════════════════════


@dataclass
class BaseAction:
    """
    Action 基类。每个子类对应一个 OneBot API。
    - action: API 名称（如 "send_group_msg"）
    - echo: 回显标识，用于配对异步响应
    """

    action: ClassVar[str] = ""  # 子类必须设置
    echo: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 OneBot Action JSON。"""
        params: Dict[str, Any] = {}
        for f in fields(self):
            if f.name == "echo":
                continue
            value = getattr(self, f.name)
            params[f.name] = value
        return {
            "action": self.action,
            "params": params,
            "echo": self.echo,
        }

    @classmethod
    def get_action_name(cls) -> str:
        """获取该 Action 对应的 API 名称。"""
        return cls.action


# ═══════════════════════════════════════════════════════════
# 消息发送类 Action
# ═══════════════════════════════════════════════════════════


@dataclass
class SendGroupMsgAction(BaseAction):
    """发送群消息。"""

    action: ClassVar[str] = "send_group_msg"
    group_id: int = 0
    message: List[Dict[str, Any]] = field(default_factory=list)
    auto_escape: bool = False


@dataclass
class SendPrivateMsgAction(BaseAction):
    """发送私聊消息。"""

    action: ClassVar[str] = "send_private_msg"
    user_id: int = 0
    message: List[Dict[str, Any]] = field(default_factory=list)
    auto_escape: bool = False


@dataclass
class SendMsgAction(BaseAction):
    """通用发送消息（自动判断群/私聊）。"""

    action: ClassVar[str] = "send_msg"
    message_type: str = "group"  # group / private
    group_id: int = 0
    user_id: int = 0
    message: List[Dict[str, Any]] = field(default_factory=list)
    auto_escape: bool = False


# ═══════════════════════════════════════════════════════════
# 信息查询类 Action
# ═══════════════════════════════════════════════════════════


@dataclass
class GetLoginInfoAction(BaseAction):
    """获取登录号信息。"""

    action: ClassVar[str] = "get_login_info"


@dataclass
class GetGroupListAction(BaseAction):
    """获取群列表。"""

    action: ClassVar[str] = "get_group_list"
    no_cache: bool = False


@dataclass
class GetGroupMemberListAction(BaseAction):
    """获取群成员列表。"""

    action: ClassVar[str] = "get_group_member_list"
    group_id: int = 0
    no_cache: bool = False


@dataclass
class GetGroupMemberInfoAction(BaseAction):
    """获取群成员信息。"""

    action: ClassVar[str] = "get_group_member_info"
    group_id: int = 0
    user_id: int = 0
    no_cache: bool = False


@dataclass
class GetMsgAction(BaseAction):
    """获取消息内容。"""

    action: ClassVar[str] = "get_msg"
    message_id: int = 0


@dataclass
class GetFriendListAction(BaseAction):
    """获取好友列表。"""

    action: ClassVar[str] = "get_friend_list"
    no_cache: bool = False


@dataclass
class GetVersionInfoAction(BaseAction):
    """获取版本信息。"""

    action: ClassVar[str] = "get_version_info"


@dataclass
class GetStatusAction(BaseAction):
    """获取运行状态。"""

    action: ClassVar[str] = "get_status"


# ═══════════════════════════════════════════════════════════
# 群管理类 Action（敏感操作）
# ═══════════════════════════════════════════════════════════


@dataclass
class SetGroupBanAction(BaseAction):
    """禁言群成员。duration=0 表示解除禁言。"""

    action: ClassVar[str] = "set_group_ban"
    group_id: int = 0
    user_id: int = 0
    duration: int = 600  # 秒，默认 10 分钟


@dataclass
class SetGroupWholeBanAction(BaseAction):
    """全员禁言。enable=True 开启。"""

    action: ClassVar[str] = "set_group_whole_ban"
    group_id: int = 0
    enable: bool = True


@dataclass
class SetGroupKickAction(BaseAction):
    """踢出群成员。"""

    action: ClassVar[str] = "set_group_kick"
    group_id: int = 0
    user_id: int = 0
    reject_add_request: bool = False  # 是否拒绝再次申请


@dataclass
class SetGroupLeaveAction(BaseAction):
    """退出群聊（敏感操作！）。"""

    action: ClassVar[str] = "set_group_leave"
    group_id: int = 0
    is_dismiss: bool = False  # 是否解散群（仅群主）


@dataclass
class SetGroupAdminAction(BaseAction):
    """设置/取消群管理员。"""

    action: ClassVar[str] = "set_group_admin"
    group_id: int = 0
    user_id: int = 0
    enable: bool = True


@dataclass
class SetGroupCardAction(BaseAction):
    """设置群名片。"""

    action: ClassVar[str] = "set_group_card"
    group_id: int = 0
    user_id: int = 0
    card: str = ""


@dataclass
class SetGroupNameAction(BaseAction):
    """设置群名称。"""

    action: ClassVar[str] = "set_group_name"
    group_id: int = 0
    group_name: str = ""


@dataclass
class SetGroupSpecialTitleAction(BaseAction):
    """设置群头衔。"""

    action: ClassVar[str] = "set_group_special_title"
    group_id: int = 0
    user_id: int = 0
    special_title: str = ""
    duration: int = -1


# ═══════════════════════════════════════════════════════════
# 好友/请求处理类 Action
# ═══════════════════════════════════════════════════════════


@dataclass
class ApproveFriendRequestAction(BaseAction):
    """同意/拒绝好友请求。"""

    action: ClassVar[str] = "set_friend_add_request"
    flag: str = ""
    approve: bool = True
    remark: str = ""


@dataclass
class ApproveGroupRequestAction(BaseAction):
    """同意/拒绝加群请求。"""

    action: ClassVar[str] = "set_group_add_request"
    flag: str = ""
    sub_type: str = "add"  # add / invite
    approve: bool = True
    reason: str = ""


# ═══════════════════════════════════════════════════════════
# 响应解析
# ═══════════════════════════════════════════════════════════


@dataclass
class ActionResponse:
    """
    Action 调用的响应回包。
    - status: "ok" / "failed" / "async"
    - retcode: 0=成功, 其他=错误码
    - data: API 返回的数据
    - echo: 与请求对应的回显标识
    """

    status: str = ""
    retcode: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    echo: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionResponse":
        return cls(
            status=str(data.get("status", "")),
            retcode=int(data.get("retcode", -1)),
            data=dict(data.get("data", {})),
            echo=str(data.get("echo", "")),
            message=str(data.get("message", "")),
        )

    @property
    def ok(self) -> bool:
        """是否调用成功。"""
        return self.status == "ok" and self.retcode == 0

    def __bool__(self) -> bool:
        return self.ok


# ═══════════════════════════════════════════════════════════
# Action 注册表（用于动态查找）
# ═══════════════════════════════════════════════════════════

ACTION_REGISTRY: Dict[str, Type[BaseAction]] = {
    cls.action: cls
    for cls in [
        SendGroupMsgAction,
        SendPrivateMsgAction,
        SendMsgAction,
        GetLoginInfoAction,
        GetGroupListAction,
        GetGroupMemberListAction,
        GetGroupMemberInfoAction,
        GetMsgAction,
        GetFriendListAction,
        GetVersionInfoAction,
        GetStatusAction,
        SetGroupBanAction,
        SetGroupWholeBanAction,
        SetGroupKickAction,
        SetGroupLeaveAction,
        SetGroupAdminAction,
        SetGroupCardAction,
        SetGroupNameAction,
        SetGroupSpecialTitleAction,
        ApproveFriendRequestAction,
        ApproveGroupRequestAction,
    ]
}


def get_action_class(action_name: str) -> Optional[Type[BaseAction]]:
    """根据 API 名称查找对应的 Action 类。"""
    return ACTION_REGISTRY.get(action_name)
