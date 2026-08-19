"""
log_mixin.py — 日志 Mixin
==========================================
监听所有事件和 Action 响应，通过 loguru 输出结构化日志。
这是最基础的 Mixin，建议优先级最高（最先记录）。
"""

from __future__ import annotations

import time
from typing import Any

from ..logger import get_logger
from ..mixin_base import BaseMixin

logger = get_logger()


class LogMixin(BaseMixin):
    """
    日志 Mixin：
    - 记录每个事件的摘要（类型、群号、用户、内容）
    - 记录每个 Action 调用的结果
    - 记录连接/断开事件
    """

    mixin_name: str = "log"
    mixin_priority: int = 0  # 最高优先级，最先记录

    def __init__(self, log_events: bool = True, log_actions: bool = True, **kwargs):
        # 吃掉可能传来的 config 等参数
        self.log_events: bool = log_events
        self.log_actions: bool = log_actions
        # 统计
        self._event_count: int = 0
        self._action_count: int = 0
        self._error_count: int = 0
        self._start_time: float = time.time()
        # 调用父类（BaseMixin）的 __init__
        super().__init__(**kwargs)

    # ─── 连接事件 ─────────────────────────────────────────

    async def mixin_on_connect(self, client: Any) -> None:
        self_id = getattr(client, "self_id", 0)
        logger.info(f"[LogMixin] WebSocket 已连接 | self_id={self_id}")

    async def mixin_on_disconnect(self, client: Any) -> None:
        logger.warning("[LogMixin] WebSocket 已断开")

    # ─── 事件日志 ─────────────────────────────────────────

    async def mixin_on_event(self, event: Any) -> None:
        if not self.log_events:
            return
        self._event_count += 1

        post_type = getattr(event, "post_type", "unknown")

        if post_type == "message":
            await self._log_message(event)
        elif post_type == "notice":
            await self._log_notice(event)
        elif post_type == "request":
            await self._log_request(event)
        elif post_type == "meta_event":
            await self._log_meta(event)

    async def _log_message(self, event: Any) -> None:
        """记录消息事件摘要。"""
        msg_type = getattr(event, "message_type", "")
        group_id = getattr(event, "group_id", 0)
        user_id = getattr(event, "user_id", 0)
        text = getattr(event, "get_message_text", lambda: "")()
        # 截断过长文本
        if len(text) > 100:
            text = text[:100] + "..."
        logger.debug(f"[消息] type={msg_type} group={group_id} " f"user={user_id} text={text!r}")

    async def _log_notice(self, event: Any) -> None:
        """记录通知事件摘要。"""
        notice_type = getattr(event, "notice_type", "")
        group_id = getattr(event, "group_id", 0)
        user_id = getattr(event, "user_id", 0)
        logger.info(f"[通知] type={notice_type} group={group_id} user={user_id}")

    async def _log_request(self, event: Any) -> None:
        """记录请求事件摘要。"""
        req_type = getattr(event, "request_type", "")
        user_id = getattr(event, "user_id", 0)
        comment = getattr(event, "comment", "")
        logger.info(f"[请求] type={req_type} user={user_id} comment={comment!r}")

    async def _log_meta(self, event: Any) -> None:
        """记录元事件（心跳/生命周期）。"""
        meta_type = getattr(event, "meta_event_type", "")
        if meta_type == "heartbeat":
            # 心跳太频繁，只记 debug
            logger.debug(f"[心跳] interval={getattr(event, 'interval', 0)}")
        else:
            logger.info(f"[元事件] type={meta_type}")

    # ─── Action 响应日志 ──────────────────────────────────

    async def mixin_on_response(self, response: Any) -> None:
        if not self.log_actions:
            return
        self._action_count += 1

        retcode = getattr(response, "retcode", -1)
        echo = getattr(response, "echo", "")

        if retcode == 0:
            logger.debug(f"[Action] OK echo={echo}")
        else:
            self._error_count += 1
            msg = getattr(response, "message", "")
            logger.error(f"[Action] FAILED echo={echo} retcode={retcode} msg={msg}")

    # ─── 关闭时输出统计 ────────────────────────────────────

    async def mixin_teardown(self) -> None:
        uptime = time.time() - self._start_time
        logger.info(
            f"[LogMixin] 统计 | 运行时长={uptime:.1f}s | "
            f"事件={self._event_count} | "
            f"Action={self._action_count} | "
            f"错误={self._error_count}"
        )

    # ─── 错误兜底 ─────────────────────────────────────────

    async def _on_error(self, exc: Exception, source, args: tuple, kwargs: dict) -> None:
        logger.error(f"[LogMixin] 内部错误: {exc}")
