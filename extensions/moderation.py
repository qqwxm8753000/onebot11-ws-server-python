"""
moderation.py — 群管助手（需审批）
====================================
演示 ConfirmManager 的敏感操作确认流程：
  /ban @某人 原因    → 提交禁言申请，管理员审批后执行
  /kick @某人 原因   → 提交踢人申请
  /leave               → 提交退群申请

管理员在控制台用 approve <token> / reject <token> 处理。
"""

from ..extension_base import BaseExtension


class ModerationExtension(BaseExtension):
    """群管助手（需审批）"""

    name = "moderation"
    version = "1.0.0"
    description = "群管操作（禁言/踢人/退群），需管理员审批"
    priority = 80

    async def on_load(self):
        self.logger.info("[Moderation] 群管插件加载（所有操作需审批）")

    async def on_group_message(self, event, client):
        text = event.get_text().strip()
        if not text.startswith(("/", "！")):
            return
        # 支持 / 和 ！两种前缀
        cmd = text[1:].strip()

        if cmd.startswith("ban "):
            await self._request_ban(event, client, cmd)
        elif cmd.startswith("kick "):
            await self._request_kick(event, client, cmd)
        elif cmd == "leave":
            await self._request_leave(event, client)

    async def _request_ban(self, event, client, cmd: str):
        """提交禁言申请"""
        # 提取被 @ 的人
        at_qq = None
        for seg in event.message:
            if seg.get("type") == "at":
                at_qq = int(seg["data"].get("qq", 0))
                break
        if not at_qq:
            await self._reply_text(event, client, "用法：/ban @某人 [时长(分钟)]")
            return

        # 解析时长（默认 10 分钟）
        parts = cmd.split()
        duration_min = 10
        if len(parts) >= 3:
            try:
                duration_min = int(parts[2])
            except ValueError:
                pass
        duration_sec = duration_min * 60

        reason = f"禁言 {duration_min} 分钟"

        # 提交审批
        token = self.confirm_manager.submit(
            action_type="set_group_ban",
            params={
                "group_id": event.group_id,
                "user_id": at_qq,
                "duration": duration_sec,
            },
            reason=reason,
            operator_qq=event.user_id,
        )
        await self._reply_text(
            event, client,
            f"⚠️ 禁言申请已提交，等待管理员审批。\n"
            f"目标: {at_qq}\n时长: {duration_min} 分钟\nToken: {token}"
        )

    async def _request_kick(self, event, client, cmd: str):
        at_qq = None
        for seg in event.message:
            if seg.get("type") == "at":
                at_qq = int(seg["data"].get("qq", 0))
                break
        if not at_qq:
            await self._reply_text(event, client, "用法：/kick @某人")
            return

        token = self.confirm_manager.submit(
            action_type="set_group_kick",
            params={
                "group_id": event.group_id,
                "user_id": at_qq,
                "reject_add_request": False,
            },
            reason=f"踢出成员 {at_qq}",
            operator_qq=event.user_id,
        )
        await self._reply_text(
            event, client,
            f"⚠️ 踢人申请已提交，等待管理员审批。\n目标: {at_qq}\nToken: {token}"
        )

    async def _request_leave(self, event, client):
        token = self.confirm_manager.submit(
            action_type="set_group_leave",
            params={
                "group_id": event.group_id,
                "is_dismiss": False,
            },
            reason=f"退出群 {event.group_id}",
            operator_qq=event.user_id,
        )
        await self._reply_text(
            event, client,
            f"⚠️ 退群申请已提交，等待管理员审批。\n群号: {event.group_id}\nToken: {token}"
        )

    async def _reply_text(self, event, client, text: str):
        from ..actions import SendGroupMsgAction
        from ..segments import build_message
        await client.send(
            SendGroupMsgAction(
                group_id=event.group_id,
                message=build_message(text),
            )
        )

    async def on_unload(self):
        self.logger.info("[Moderation] 群管插件卸载")
