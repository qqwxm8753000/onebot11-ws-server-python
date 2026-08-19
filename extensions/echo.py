"""
echo.py — 复读机插件
============================
群内发送 /echo 任意内容 → 机器人复读该内容
演示 Extension 最基础写法。
"""

from ..extension_base import BaseExtension
from ..actions import SendGroupMsgAction
from ..segments import build_message


class EchoExtension(BaseExtension):
    """复读机"""

    name = "echo"
    version = "1.0.0"
    description = "群内 /echo 复读"
    priority = 100

    async def on_load(self):
        self.logger.info("[Echo] 插件加载")

    async def on_group_message(self, event, client):
        text = event.get_text().strip()
        if not text.startswith("/echo "):
            return
        content = text[len("/echo "):].strip()
        if not content:
            content = "（空复读）"
        await client.send(
            SendGroupMsgAction(
                group_id=event.group_id,
                message=build_message(content),
            )
        )

    async def on_unload(self):
        self.logger.info("[Echo] 插件卸载")
