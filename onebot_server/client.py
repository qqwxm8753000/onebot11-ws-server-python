"""
client.py — OneBot 客户端
==========================================
封装与 LLOneBot 的 WebSocket 连接，提供：
  - send(action): 发送 Action 不等回包
  - call(action): 发送 Action 并等待回包
  - 自动 echo 配对
  - 断线检测
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from .actions import ActionResponse, BaseAction


class OneBotClient:
    """
    OneBot 客户端，绑定一条 WebSocket 连接。
    Handler 和 Mixin 通过此客户端与 LLOneBot 交互。
    """

    def __init__(
        self,
        websocket: Any,  # websockets.WebSocketServerProtocol
        self_id: int = 0,
        action_timeout: int = 10,
    ):
        self._ws = websocket
        self.self_id: int = self_id
        self._action_timeout: int = action_timeout

        # echo → Future 映射表
        self._pending: Dict[str, asyncio.Future] = {}
        # 写锁（WebSocket 发送需串行）
        self._write_lock = asyncio.Lock()
        # 连接建立时间
        self.connected_at: float = time.time()
        # 最后活跃时间
        self.last_active: float = time.time()
        # 是否已关闭
        self._closed: bool = False

    # ─── 连接状态 ──────────────────────────────────────────

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def uptime(self) -> float:
        """连接持续时间（秒）。"""
        return time.time() - self.connected_at

    # ─── 发送 Action ───────────────────────────────────────

    async def send(self, action: BaseAction) -> str:
        """
        发送 Action，不等待回包。返回 echo 标识。
        """
        self.last_active = time.time()
        payload = json.dumps(action.to_dict(), ensure_ascii=False)
        async with self._write_lock:
            await self._ws.send(payload)
        return action.echo

    async def call(
        self,
        action: BaseAction,
        timeout: Optional[int] = None,
    ) -> ActionResponse:
        """
        发送 Action 并等待回包。
        返回 ActionResponse，可通过 .ok 判断是否成功。
        """
        self.last_active = time.time()
        echo = action.echo
        to = timeout or self._action_timeout

        # 注册 Future（用 get_running_loop 兼容 Python 3.12+）
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[echo] = future

        try:
            payload = json.dumps(action.to_dict(), ensure_ascii=False)
            async with self._write_lock:
                await self._ws.send(payload)

            # 等待响应
            result = await asyncio.wait_for(future, timeout=to)
            return result
        except asyncio.TimeoutError:
            return ActionResponse(
                status="failed",
                retcode=-1,
                echo=echo,
                message=f"调用超时（{to}s）",
            )
        finally:
            self._pending.pop(echo, None)

    # ─── 接收响应 ──────────────────────────────────────────

    async def handle_response(self, raw: str) -> Optional[ActionResponse]:
        """
        处理来自 LLOneBot 的响应数据。
        如果是 Action 回包则配对 Future，否则返回 None。
        """
        self.last_active = time.time()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        # 判断是否为 Action 响应（有 echo 且有 status）
        echo = str(data.get("echo", ""))
        if echo and echo in self._pending:
            resp = ActionResponse.from_dict(data)
            future = self._pending.get(echo)
            if future and not future.done():
                future.set_result(resp)
            return resp

        # 也可能是事件推送（没有 echo 或不在 pending 中）
        return None

    # ─── 便捷方法 ──────────────────────────────────────────

    async def send_group_msg(
        self,
        group_id: int,
        message: list,
        auto_escape: bool = False,
    ) -> ActionResponse:
        """快捷方法：发送群消息。"""
        from .actions import SendGroupMsgAction

        return await self.call(
            SendGroupMsgAction(
                group_id=group_id,
                message=message,
                auto_escape=auto_escape,
            )
        )

    async def send_private_msg(
        self,
        user_id: int,
        message: list,
        auto_escape: bool = False,
    ) -> ActionResponse:
        """快捷方法：发送私聊消息。"""
        from .actions import SendPrivateMsgAction

        return await self.call(
            SendPrivateMsgAction(
                user_id=user_id,
                message=message,
                auto_escape=auto_escape,
            )
        )

    async def get_login_info(self) -> ActionResponse:
        """快捷方法：获取登录号信息。"""
        from .actions import GetLoginInfoAction

        return await self.call(GetLoginInfoAction())

    async def get_group_list(self, no_cache: bool = False) -> ActionResponse:
        """快捷方法：获取群列表。"""
        from .actions import GetGroupListAction

        return await self.call(GetGroupListAction(no_cache=no_cache))

    async def get_group_member_list(self, group_id: int, no_cache: bool = False) -> ActionResponse:
        """快捷方法：获取群成员列表。"""
        from .actions import GetGroupMemberListAction

        return await self.call(GetGroupMemberListAction(group_id=group_id, no_cache=no_cache))

    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 600) -> ActionResponse:
        """快捷方法：禁言群成员。"""
        from .actions import SetGroupBanAction

        return await self.call(SetGroupBanAction(group_id=group_id, user_id=user_id, duration=duration))

    async def set_group_kick(self, group_id: int, user_id: int, reject_add: bool = False) -> ActionResponse:
        """快捷方法：踢出群成员。"""
        from .actions import SetGroupKickAction

        return await self.call(SetGroupKickAction(group_id=group_id, user_id=user_id, reject_add_request=reject_add))

    async def set_group_leave(self, group_id: int, is_dismiss: bool = False) -> ActionResponse:
        """快捷方法：退出群聊。"""
        from .actions import SetGroupLeaveAction

        return await self.call(SetGroupLeaveAction(group_id=group_id, is_dismiss=is_dismiss))

    # ─── 关闭 ──────────────────────────────────────────────

    async def close(self) -> None:
        """关闭连接并清理所有待处理请求。"""
        self._closed = True
        # 取消所有 pending future
        for echo, future in self._pending.items():
            if not future.done():
                future.cancel()
        self._pending.clear()
        # 关闭 WebSocket
        try:
            await self._ws.close()
        except Exception:
            pass
