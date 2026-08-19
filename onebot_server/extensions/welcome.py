"""
welcome.py — 入群欢迎插件
==========================================
功能：
  - 新人入群时自动发送欢迎消息
  - 有人退群时记录日志
演示 Extension 处理 Notice 事件。
"""

from typing import Any

from onebot_server import (
    BaseExtension,
    GroupNoticeEvent,
    at_segment,
    build_message,
    text_segment,
)


class WelcomeExtension(BaseExtension):
    """入群欢迎 & 退群记录。"""

    ext_name: str = "welcome"
    description: str = "新人入群欢迎 + 退群记录"
    priority: int = 30
    version: str = "1.0.0"

    async def ext_on_notice(self, event: Any) -> None:
        """处理通知事件。"""
        if not isinstance(event, GroupNoticeEvent):
            return

        notice_type = getattr(event, "notice_type", "")

        if notice_type == "group_increase":
            await self._welcome_new_member(event)
        elif notice_type == "group_decrease":
            await self._log_member_leave(event)

    async def _welcome_new_member(self, event: GroupNoticeEvent) -> None:
        """欢迎新人入群。"""
        group_id = event.group_id
        user_id = event.user_id

        # 获取昵称
        nickname = ""
        sender = getattr(event, "sender", None)
        if sender:
            nickname = getattr(sender, "nickname", "")

        welcome_text = "🎉 欢迎 " if not nickname else f"🎉 欢迎 {nickname}"

        message = build_message(
            at_segment(user_id),
            text_segment(f" {welcome_text}加入本群！\n请阅读群公告，文明交流～"),
        )

        await self.safe_send_group_msg(
            group_id=group_id,
            message=message,
        )

    async def _log_member_leave(self, event: GroupNoticeEvent) -> None:
        """记录有人退群/被踢。"""
        group_id = event.group_id
        user_id = event.user_id
        sub_type = getattr(event, "sub_type", "")

        reason_map = {
            "leave": "主动退群",
            "kick": "被踢出",
            "disband": "群解散",
        }
        reason = reason_map.get(sub_type, "离开群聊")

        self.logger.info(f"[Welcome] 群 {group_id} | {user_id} {reason}")

        # 可选：通知群内
        if sub_type == "kick":
            message = build_message(
                text_segment(f"📢 用户 {user_id} 已被踢出群聊"),
            )
            await self.safe_send_group_msg(
                group_id=group_id,
                message=message,
            )
