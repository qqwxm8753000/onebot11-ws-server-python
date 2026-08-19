"""
echo.py — 复读机插件
==========================================
功能：群内 @机器人 /echo <内容> → 复读内容
演示 Extension 的基本写法。
"""


from onebot_server import (
    BaseExtension,
    GroupMessageEvent,
    at_segment,
    build_message,
    reply_segment,
    text_segment,
)


class EchoExtension(BaseExtension):
    """复读机：将用户发送的内容原样返回。"""

    ext_name: str = "echo"
    description: str = "复读机插件：@机器人 /echo <内容>"
    priority: int = 10
    version: str = "1.0.0"

    async def ext_on_group_message(self, event: GroupMessageEvent) -> None:
        """监听群消息，处理 /echo 命令。"""
        text = event.get_message_text().strip()

        # 检查是否以 /echo 开头
        if not text.startswith("/echo"):
            return

        # 提取要复读的内容
        content = text[5:].strip()
        if not content:
            content = "（空内容）"

        # 构造回复：引用原消息 + @发送者 + 复读内容
        message = build_message(
            reply_segment(event.message_id),
            at_segment(event.user_id),
            text_segment(f" {content}"),
        )

        # 发送回复
        await self.safe_send_group_msg(
            group_id=event.group_id,
            message=message,
        )
