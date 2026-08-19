"""
welcome.py — 入群欢迎
========================
有人加入群时，发送欢迎语。
"""

from ..extension_base import BaseExtension
from ..actions import SendGroupMsgAction
from ..segments import build_message


class WelcomeExtension(BaseExtension):
    """入群欢迎"""

    name = "welcome"
    version = "1.0.0"
    description = "新人入群欢迎"
    priority = 70

    WELCOME_TEXT = (
        "🎉 欢迎新成员加入本群！\n"
        "请先阅读群公告，有问题随时提问哦~\n"
        "输入「帮助」查看机器人功能。"
    )

    async def on_load(self):
        self.logger.info("[Welcome] 入群欢迎插件加载")

    async def on_notice(self, event, client):
        """监听通知事件"""
        notice_type = getattr(event, "notice_type", "")
        if notice_type == "group_increase":
            group_id = event.group_id
            user_id = event.user_id
            text = f"🎉 欢迎 <@{user_id}> 加入群 {group_id}！\n{self.WELCOME_TEXT}"
            await client.send(
                SendGroupMsgAction(
                    group_id=group_id,
                    message=build_message(text),
                )
            )

    async def on_unload(self):
        self.logger.info("[Welcome] 入群欢迎插件卸载")
