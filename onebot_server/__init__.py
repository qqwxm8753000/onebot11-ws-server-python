"""
onebot_server — OneBot 11 WebSocket 服务器
==========================================
自写 QQ 机器人后端，对接 LLOneBot。
支持 Mixin 组合 + Extension 热加载 + 敏感操作确认 + 自动备份。

快速开始:
    from onebot_server import OneBotServer
    server = OneBotServer("config.toml")
    server.run_forever()

命令行:
    python -m onebot_server.server -c config.toml
"""

from .actions import (
    ACTION_REGISTRY,
    ActionResponse,
    ApproveFriendRequestAction,
    ApproveGroupRequestAction,
    BaseAction,
    GetFriendListAction,
    GetGroupListAction,
    GetGroupMemberInfoAction,
    GetGroupMemberListAction,
    GetLoginInfoAction,
    GetMsgAction,
    GetStatusAction,
    GetVersionInfoAction,
    SendGroupMsgAction,
    SendMsgAction,
    SendPrivateMsgAction,
    SetGroupAdminAction,
    SetGroupBanAction,
    SetGroupCardAction,
    SetGroupKickAction,
    SetGroupLeaveAction,
    SetGroupNameAction,
    SetGroupSpecialTitleAction,
    SetGroupWholeBanAction,
    at_segment,
    build_message,
    face_segment,
    get_action_class,
    image_segment,
    reply_segment,
    text_segment,
)
from .client import OneBotClient
from .config import Config, get_config
from .confirm import ConfirmManager, ConfirmRequest
from .events import (
    BaseEvent,
    FriendRequestEvent,
    GroupMessageEvent,
    GroupNoticeEvent,
    GroupRequestEvent,
    MessageEvent,
    MessageSegment,
    MetaEvent,
    NoticeEvent,
    PrivateMessageEvent,
    RequestEvent,
    UnknownEvent,
    parse_message,
)
from .extension_base import BaseExtension
from .extension_manager import ExtensionManager
from .handler import OneBotHandler, create_handler_class
from .logger import get_logger, init_logger
from .mixin_base import BaseMixin
from .server import OneBotServer
from .whitelist import WhitelistManager

__version__ = "2.0.0"
__all__ = [
    # 核心
    "OneBotServer",
    "OneBotHandler",
    "OneBotClient",
    # 配置
    "Config",
    "get_config",
    # 日志
    "init_logger",
    "get_logger",
    # 事件
    "BaseEvent",
    "MessageEvent",
    "GroupMessageEvent",
    "PrivateMessageEvent",
    "NoticeEvent",
    "GroupNoticeEvent",
    "RequestEvent",
    "GroupRequestEvent",
    "FriendRequestEvent",
    "MetaEvent",
    "UnknownEvent",
    "MessageSegment",
    "parse_message",
    # Action
    "BaseAction",
    "ActionResponse",
    "SendGroupMsgAction",
    "SendPrivateMsgAction",
    "SendMsgAction",
    "GetLoginInfoAction",
    "GetGroupListAction",
    "GetGroupMemberListAction",
    "GetGroupMemberInfoAction",
    "GetMsgAction",
    "GetFriendListAction",
    "GetVersionInfoAction",
    "GetStatusAction",
    "SetGroupBanAction",
    "SetGroupWholeBanAction",
    "SetGroupKickAction",
    "SetGroupLeaveAction",
    "SetGroupAdminAction",
    "SetGroupCardAction",
    "SetGroupNameAction",
    "SetGroupSpecialTitleAction",
    "ApproveFriendRequestAction",
    "ApproveGroupRequestAction",
    "text_segment",
    "image_segment",
    "at_segment",
    "face_segment",
    "reply_segment",
    "build_message",
    "ACTION_REGISTRY",
    "get_action_class",
    # 确认 & 白名单
    "ConfirmManager",
    "ConfirmRequest",
    "WhitelistManager",
    # Mixin & Extension
    "BaseMixin",
    "BaseExtension",
    "ExtensionManager",
    "create_handler_class",
]
