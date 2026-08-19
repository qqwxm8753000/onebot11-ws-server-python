"""
moderation.py — 群管助手插件
==========================================
功能：
  - /banme       — 禁言自己（演示确认流程）
  - /ban <@谁>   — 禁言他人（需管理员审批）
  - /kick <@谁>  — 踢人（需管理员审批）
  - /leave       — 退群（需管理员审批，触发自动备份）
演示 Extension 如何提交敏感操作到确认队列。
"""

import re

from onebot_server.extension_base import BaseExtension
from onebot_server import (  # noqa: F401
    GroupMessageEvent,
    SetGroupBanAction,
    at_segment,
    build_message,
    text_segment,
)


class ModerationExtension(BaseExtension):
    """群管助手：敏感操作需审批。"""

    ext_name: str = "moderation"
    description: str = "群管助手（禁言/踢人/退群，需审批）"
    priority: int = 5  # 较高优先级，尽早拦截
    version: str = "1.0.0"

    async def ext_on_group_message(self, event: GroupMessageEvent) -> None:
        """处理群管命令。"""
        text = event.get_message_text().strip()
        group_id = event.group_id
        user_id = event.user_id

        # /banme — 禁言自己 60 秒
        if text == "/banme":
            await self._ban_self(group_id, user_id)
            return

        # /ban @xxx [duration] — 禁言他人
        if text.startswith("/ban"):
            await self._ban_other(event, text)
            return

        # /kick @xxx — 踢人
        if text.startswith("/kick"):
            await self._kick_user(event, text)
            return

        # /leave — 退群
        if text == "/leave":
            await self._leave_group(event)
            return

    async def _ban_self(self, group_id: int, user_id: int) -> None:
        """禁言自己（不需要审批，仅自己受影响）。"""
        client = self.client
        if not client:
            return

        action = SetGroupBanAction(
            group_id=group_id,
            user_id=user_id,
            duration=60,  # 60秒
        )
        resp = await client.call(action)
        if resp.ok:
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(
                    at_segment(user_id),
                    text_segment(" 已禁言自己 60 秒 🤐"),
                ),
            )
        else:
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(
                    text_segment(f"禁言失败 (retcode={resp.retcode})"),
                ),
            )

    async def _ban_other(self, event: GroupMessageEvent, text: str) -> None:
        """禁言他人（需审批）。"""
        # 解析目标用户（从消息段中提取 @）
        target_id = self._extract_at_user(event)
        if not target_id:
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=build_message(text_segment("用法: /ban @某人 [秒数]")),
            )
            return

        # 解析时长
        duration = 600  # 默认 10 分钟
        match = re.search(r"(\d+)", text)
        if match:
            duration = int(match.group(1))

        # 提交确认
        handler = self.handler
        if handler and hasattr(handler, "submit_sensitive_action"):
            token = await handler.submit_sensitive_action(
                action_type="set_group_ban",
                params={
                    "group_id": event.group_id,
                    "user_id": target_id,
                    "duration": duration,
                },
                description=f"禁言 {target_id} 在群 {event.group_id}（{duration}秒）",
                executor=event.user_id,
            )
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=build_message(
                    at_segment(event.user_id),
                    text_segment(
                        f" 禁言请求已提交审批\n"
                        f"令牌: {token}\n"
                        f"目标: {target_id}\n"
                        f"时长: {duration}秒\n"
                        f"等待管理员批准..."
                    ),
                ),
            )

    async def _kick_user(self, event: GroupMessageEvent, text: str) -> None:
        """踢人（需审批）。"""
        target_id = self._extract_at_user(event)
        if not target_id:
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=build_message(text_segment("用法: /kick @某人")),
            )
            return

        handler = self.handler
        if handler and hasattr(handler, "submit_sensitive_action"):
            token = await handler.submit_sensitive_action(
                action_type="set_group_kick",
                params={
                    "group_id": event.group_id,
                    "user_id": target_id,
                },
                description=f"踢出 {target_id} 从群 {event.group_id}",
                executor=event.user_id,
            )
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=build_message(
                    text_segment(f"踢人请求已提交审批，令牌: {token}"),
                ),
            )

    async def _leave_group(self, event: GroupMessageEvent) -> None:
        """退群（需审批 + 自动备份）。"""
        handler = self.handler
        if not handler:
            return

        group_id = event.group_id
        token = await handler.submit_sensitive_action(
            action_type="set_group_leave",
            params={"group_id": group_id},
            description=f"退出群聊 {group_id}",
            executor=event.user_id,
        )

        # 通知
        await self.safe_send_group_msg(
            group_id=group_id,
            message=build_message(
                text_segment(
                    f"⚠ 退群请求已提交审批\n"
                    f"令牌: {token}\n"
                    f"退群前将自动备份白名单和群列表\n"
                    f"等待管理员批准..."
                ),
            ),
        )

    def _extract_at_user(self, event: GroupMessageEvent) -> int:
        """从消息段中提取被 @ 的用户 ID。"""
        for seg in event.message:
            if seg.type == "at":
                qq = seg.data.get("qq", "")
                if qq and qq != "all":
                    try:
                        return int(qq)
                    except ValueError:
                        pass
        return 0
