"""
confirm.py — 敏感操作确认管理器
==========================================
退群、踢人、全员禁言等敏感操作需要先生成确认令牌，
由管理员审批后才能执行。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class ConfirmRequest:
    """
    一条待确认的敏感操作请求。
    - token: 唯一标识
    - action_type: 操作类型（leave_group / kick / whole_ban 等）
    - params: 操作参数
    - description: 人类可读的描述
    - created_at: 创建时间戳
    - timeout: 超时秒数
    - approved: 是否已批准
    - rejected: 是否被拒绝
    - executor: 提交者的 QQ 号
    """

    token: str
    action_type: str
    params: Dict[str, Any]
    description: str
    created_at: float
    timeout: int
    approved: bool = False
    rejected: bool = False
    executor: int = 0
    future: Optional[asyncio.Future] = field(default=None, repr=False)

    def is_expired(self, now: Optional[float] = None) -> bool:
        """判断是否已超时。"""
        if now is None:
            now = time.time()
        return (now - self.created_at) > self.timeout

    def status(self) -> str:
        """返回当前状态文本。"""
        if self.rejected:
            return "已拒绝"
        if self.approved:
            return "已批准"
        if self.is_expired():
            return "已超时"
        return "等待审批"


class ConfirmManager:
    """
    确认管理器。
    - 提交请求 → 返回 token
    - 管理员审批 → 触发回调执行
    - 超时自动清理
    """

    def __init__(self, timeout: int = 300):
        self._timeout = timeout
        self._requests: Dict[str, ConfirmRequest] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        action_type: str,
        params: Dict[str, Any],
        description: str,
        executor: int = 0,
        timeout: Optional[int] = None,
    ) -> str:
        """
        提交一条敏感操作请求，返回 token。
        调用方应等待 token 对应的审批结果。
        """
        token = uuid.uuid4().hex[:16]
        to = timeout or self._timeout
        req = ConfirmRequest(
            token=token,
            action_type=action_type,
            params=params,
            description=description,
            created_at=time.time(),
            timeout=to,
            executor=executor,
        )
        # 创建 Future 用于异步等待（get_running_loop 兼容 3.12+）
        loop = asyncio.get_running_loop()
        req.future = loop.create_future()

        async with self._lock:
            self._requests[token] = req

        return token

    async def wait_for_approval(self, token: str, timeout: Optional[int] = None) -> bool:
        """
        等待审批结果。返回 True=批准，False=拒绝/超时。
        """
        req = self._requests.get(token)
        if not req or not req.future:
            return False
        to = timeout or req.timeout
        try:
            result = await asyncio.wait_for(req.future, timeout=to)
            return bool(result)
        except asyncio.TimeoutError:
            req.rejected = True
            return False

    async def approve(self, token: str, admin_id: int = 0) -> Tuple[bool, str]:
        """
        管理员批准操作。
        返回 (是否成功, 消息)。
        """
        async with self._lock:
            req = self._requests.get(token)
            if not req:
                return False, f"令牌 {token} 不存在"
            if req.is_expired():
                del self._requests[token]
                return False, "请求已超时"
            if req.approved or req.rejected:
                return False, f"请求已处理（{req.status()}）"
            req.approved = True

        # 唤醒等待者
        if req.future and not req.future.done():
            req.future.set_result(True)

        return True, f"已批准: {req.description}"

    async def reject(self, token: str, admin_id: int = 0) -> Tuple[bool, str]:
        """
        管理员拒绝操作。
        """
        async with self._lock:
            req = self._requests.get(token)
            if not req:
                return False, f"令牌 {token} 不存在"
            if req.is_expired():
                del self._requests[token]
                return False, "请求已超时"
            if req.approved or req.rejected:
                return False, f"请求已处理（{req.status()}）"
            req.rejected = True

        if req.future and not req.future.done():
            req.future.set_result(False)

        return True, f"已拒绝: {req.description}"

    async def list_pending(self) -> list[Dict[str, Any]]:
        """列出所有待审批请求。"""
        async with self._lock:
            await self._cleanup_expired()
            result = []
            for req in self._requests.values():
                if not req.approved and not req.rejected:
                    result.append(
                        {
                            "token": req.token,
                            "action_type": req.action_type,
                            "description": req.description,
                            "executor": req.executor,
                            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(req.created_at)),
                            "expires_in": max(0, int(req.timeout - (time.time() - req.created_at))),
                            "status": req.status(),
                        }
                    )
            return result

    def get(self, token: str) -> Optional[ConfirmRequest]:
        """获取请求详情。"""
        return self._requests.get(token)

    async def _cleanup_expired(self) -> None:
        """清理已超时的请求。"""
        now = time.time()
        expired = [
            t for t, req in self._requests.items() if req.is_expired(now) and not req.approved and not req.rejected
        ]
        for t in expired:
            req = self._requests.pop(t)
            if req.future and not req.future.done():
                req.future.set_result(False)

    async def cleanup_task(self, interval: int = 60) -> None:
        """
        后台清理任务，定期移除过期请求。
        可在 asyncio 事件循环中作为任务运行。
        """
        while True:
            await asyncio.sleep(interval)
            async with self._lock:
                await self._cleanup_expired()
