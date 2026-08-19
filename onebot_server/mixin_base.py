"""
mixin_base.py — Mixin 基类
==========================================
所有 Mixin 必须继承 BaseMixin。
Mixin 通过多重继承被组合到 Handler 中，
也可以被其他 Mixin 继承（Mixin 套 Mixin）。
"""

from __future__ import annotations

import inspect
from typing import Any, List, Set, Type


class BaseMixin:
    """
    Mixin 基类。所有功能模块（日志、备份、控制台、任务调度等）
    都通过继承此类实现，最终被 OneBotHandler 多重继承组合。

    生命周期钩子（由 Handler 在适当时机调用）：
      - mixin_setup(handler)     初始化（连接建立前）
      - mixin_on_connect(client) 连接建立后
      - mixin_on_event(event)    每个事件到达时
      - mixin_on_message(event)  每条消息到达时
      - mixin_on_response(resp)  每个 Action 回包到达时
      - mixin_teardown()         关闭时清理

    注意：所有钩子都是 async 可选的——如果子类没定义或不是协程，
    框架会自动适配。
    """

    # ─── 类属性（子类可覆盖）──────────────────────────────
    # Mixin 名称（用于日志和优先级排序）
    mixin_name: str = "base"
    # 优先级（数字越小越先执行，0=最高）
    mixin_priority: int = 100
    # 该 Mixin 是否启用
    mixin_enabled: bool = True

    def __init_subclass__(cls, **kwargs):
        """子类注册时自动收集钩子信息。"""
        super().__init_subclass__(**kwargs)
        # 自动从类名推导 mixin_name
        if cls.mixin_name == "base" and cls is not BaseMixin:
            cls.mixin_name = cls.__name__.lower().replace("mixin", "")

    # ─── 生命周期：初始化 ──────────────────────────────────

    async def mixin_setup(self, handler: Any) -> None:
        """
        初始化钩子。Handler 构造时调用。
        可在此处创建后台任务、打开文件等。
        """
        pass

    # ─── 生命周期：连接建立 ────────────────────────────────

    async def mixin_on_connect(self, client: Any) -> None:
        """WebSocket 连接建立后调用。"""
        pass

    async def mixin_on_disconnect(self, client: Any) -> None:
        """WebSocket 连接断开后调用。"""
        pass

    # ─── 生命周期：事件处理 ────────────────────────────────

    async def mixin_on_event(self, event: Any) -> None:
        """
        每个事件到达时调用（在 Handler 分发之前）。
        可在此处做全局拦截、统计、日志等。
        """
        pass

    async def mixin_on_message(self, event: Any) -> None:
        """每条消息事件到达时调用。"""
        pass

    async def mixin_on_notice(self, event: Any) -> None:
        """每条通知事件到达时调用。"""
        pass

    async def mixin_on_request(self, event: Any) -> None:
        """每条请求事件到达时调用。"""
        pass

    async def mixin_on_meta(self, event: Any) -> None:
        """每条元事件到达时调用。"""
        pass

    async def mixin_on_response(self, response: Any) -> None:
        """每个 Action 响应回包到达时调用。"""
        pass

    # ─── 生命周期：关闭 ────────────────────────────────────

    async def mixin_teardown(self) -> None:
        """Handler 关闭时调用。清理资源。"""
        pass

    # ─── 工具方法 ──────────────────────────────────────────

    def is_enabled(self) -> bool:
        """检查该 Mixin 是否启用。"""
        return getattr(self, "mixin_enabled", True)

    def set_enabled(self, enabled: bool) -> None:
        """运行时启用/禁用该 Mixin。"""
        self.mixin_enabled = enabled

    async def _safe_call(self, coro_or_func, *args, **kwargs) -> Any:
        """
        安全调用：如果是协程就 await，否则直接调用。
        捕获异常并返回 None，不向上传播。
        """
        try:
            result = coro_or_func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            # 子类可重写 _on_error 做自定义处理
            await self._on_error(e, coro_or_func, args, kwargs)
            return None

    async def _on_error(self, exc: Exception, source, args: tuple, kwargs: dict) -> None:
        """Mixin 内部错误兜底。子类可重写。"""
        pass

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.mixin_name} "
            f"priority={self.mixin_priority} "
            f"enabled={self.is_enabled()}>"
        )


# ═══════════════════════════════════════════════════════════
# Mixin 组合工具
# ═══════════════════════════════════════════════════════════


def collect_mixins(cls: Type) -> List[Type[BaseMixin]]:
    """
    收集一个类的所有 BaseMixin 子类（按优先级排序）。
    多重继承时，按 MRO 顺序去重。
    """
    mixins: List[Type[BaseMixin]] = []
    seen: Set[Type] = set()
    for base in cls.__mro__:
        if base is BaseMixin or not issubclass(base, BaseMixin):
            continue
        if base in seen:
            continue
        seen.add(base)
        mixins.append(base)

    # 按优先级排序（数字小的在前）
    mixins.sort(key=lambda m: getattr(m, "mixin_priority", 100))
    return mixins


def get_mixin_instances(handler: Any) -> List[BaseMixin]:
    """
    从 Handler 实例中提取所有 Mixin 实例（按优先级排序）。
    """
    instances: List[BaseMixin] = []
    seen: Set[int] = set()
    for attr_name in dir(handler):
        try:
            attr = getattr(handler, attr_name)
        except Exception:
            continue
        if isinstance(attr, BaseMixin):
            obj_id = id(attr)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            instances.append(attr)

    instances.sort(key=lambda m: getattr(m, "mixin_priority", 100))
    return instances
