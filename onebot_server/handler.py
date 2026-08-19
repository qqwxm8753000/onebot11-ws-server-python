"""
handler.py — OneBotHandler（核心枢纽）
==========================================
通过多重继承组合所有 Mixin，
负责：
  - 事件分发（消息 → 通知 → 请求 → 元事件）
  - Mixin 生命周期管理
  - Extension 注册与调用
  - 确认管理器集成
  - 白名单管理
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Type

from .actions import ActionResponse
from .client import OneBotClient
from .config import Config
from .confirm import ConfirmManager
from .events import (  # noqa: F401
    BaseEvent,
    GroupMessageEvent,
    MessageEvent,
    MetaEvent,
    NoticeEvent,
    PrivateMessageEvent,
    RequestEvent,
    UnknownEvent,
)
from .extension_base import BaseExtension
from .extension_manager import ExtensionManager
from .logger import get_logger
from .mixin_base import BaseMixin
from .whitelist import WhitelistManager

logger = get_logger()


class OneBotHandler(
    # Mixin 在此处通过多重继承组合
    # 实际 Mixin 列表在 Server 中动态组装
):
    """
    OneBot 事件处理器。
    通过 Mixin 组合获得功能，Extension 在运行时动态注册。

    属性：
      - client:       OneBotClient 实例
      - config:       配置对象
      - self_id:      当前登录 QQ 号
      - whitelist:    白名单管理器
      - confirm_manager: 确认管理器
      - extensions:   已注册的 Extension 字典
    """

    def __init__(
        self,
        config: Config,
        whitelist: Optional[WhitelistManager] = None,
        confirm_manager: Optional[ConfirmManager] = None,
    ):
        self.config: Config = config
        self.whitelist: WhitelistManager = whitelist or WhitelistManager(data_dir="data")
        self.confirm_manager: ConfirmManager = confirm_manager or ConfirmManager(timeout=config.confirm_timeout)

        # 核心引用
        self.client: Optional[OneBotClient] = None
        self.self_id: int = 0

        # Extension 管理
        self.extension_manager: Optional[ExtensionManager] = None
        self.extensions: Dict[str, BaseExtension] = {}

        # 运行状态
        self._running: bool = False
        self._start_time: float = 0.0

        # Mixin 代理缓存（按优先级排序）
        self._mixin_proxies: List[Any] = []

        logger.debug("[Handler] 初始化完成")

    # ═══════════════════════════════════════════════════
    # Mixin 管理
    # ═══════════════════════════════════════════════════

    def _collect_mixins(self) -> List[Any]:
        """
        收集当前类所有 Mixin 的代理对象（按优先级排序）。

        遍历 MRO，为每个 BaseMixin 子类创建 _MixinProxy。
        Proxy 只暴露该 Mixin 自身定义的方法，避免多重继承下
        方法解析顺序导致的重复触发。
        """
        seen: Set[type] = set()
        proxies: List[Any] = []

        for cls in self.__class__.__mro__:
            if cls is BaseMixin or not issubclass(cls, BaseMixin):
                continue
            if cls in seen:
                continue
            seen.add(cls)

            # 排除动态 Handler 类自身（动态生成的类在 __module__ 为 onebot_server.handler）
            if cls.__module__ == __name__ and cls is not BaseMixin:
                continue

            proxy = _MixinProxy(cls, self)
            proxies.append(proxy)

        # 按优先级排序（数字小=先执行）
        proxies.sort(key=lambda p: p.mixin_priority)
        self._mixin_proxies = proxies
        return proxies

    async def _setup_mixins(self) -> None:
        """调用所有 Mixin 的 mixin_setup 钩子。"""
        for proxy in self._mixin_proxies:
            method = proxy.mixin_setup
            if not method:
                continue
            try:
                await method(self)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} setup 失败: {e}")

    async def _teardown_mixins(self) -> None:
        """调用所有 Mixin 的 mixin_teardown 钩子（逆序）。"""
        for proxy in reversed(self._mixin_proxies):
            method = proxy.mixin_teardown
            if not method:
                continue
            try:
                await method()
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} teardown 失败: {e}")

    # ═══════════════════════════════════════════════════
    # Extension 管理
    # ═══════════════════════════════════════════════════

    def add_extension(self, name: str, ext: BaseExtension) -> None:
        """注册 Extension 到 Handler。"""
        self.extensions[name] = ext
        ext.handler = self
        # 如果 client 已就绪，通知 extension
        if self.client:
            asyncio.create_task(ext.ext_on_connect(self.client))

    def remove_extension(self, name: str) -> None:
        """从 Handler 移除 Extension。"""
        ext = self.extensions.pop(name, None)
        if ext:
            ext.handler = None

    def get_extension(self, name: str) -> Optional[BaseExtension]:
        """获取 Extension 实例。"""
        return self.extensions.get(name)

    # ═══════════════════════════════════════════════════
    # 连接管理
    # ═══════════════════════════════════════════════════

    async def attach_client(self, client: OneBotClient) -> None:
        """
        绑定 WebSocket 客户端并启动所有 Mixin/Extension。
        """
        self.client = client
        self.self_id = client.self_id
        self._running = True
        self._start_time = time.time()

        # 收集并初始化 Mixin
        self._collect_mixins()
        await self._setup_mixins()

        # 通知所有 Extension 连接就绪
        for ext in self.extensions.values():
            try:
                await ext.ext_on_connect(client)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_connect 失败: {e}")

        # 调用 Mixin 连接钩子
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_connect
            if not method:
                continue
            try:
                await method(client)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_connect 失败: {e}")

        logger.info(f"[Handler] 连接就绪 | self_id={self.self_id}")

    async def detach_client(self, client: OneBotClient) -> None:
        """断开连接，清理资源。"""
        # 通知 Mixin
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_disconnect
            if not method:
                continue
            try:
                await method(client)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_disconnect 失败: {e}")

        # 通知 Extension
        for ext in self.extensions.values():
            try:
                await ext.ext_on_disconnect(client)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_disconnect 失败: {e}")

        self._running = False
        logger.info("[Handler] 连接已断开")

    # ═══════════════════════════════════════════════════
    # 事件分发（核心）
    # ═══════════════════════════════════════════════════

    async def handle_event(self, raw_data: dict) -> None:
        """
        事件总入口。解析 → 分发 → 调用 Mixin + Extension。
        """
        # 解析事件
        event = BaseEvent.from_dict(raw_data)

        # 如果是 meta_event 且包含 self_id，更新
        if isinstance(event, MetaEvent):
            if event.self_id and not self.self_id:
                self.self_id = event.self_id
                if self.client:
                    self.client.self_id = event.self_id

        # 分发到 Mixin（通用事件钩子）
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_event
            if not method:
                continue
            try:
                await method(event)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_event 错误: {e}")

        # 按类型分发到具体钩子
        if isinstance(event, MessageEvent):
            await self._dispatch_message(event)
        elif isinstance(event, NoticeEvent):
            await self._dispatch_notice(event)
        elif isinstance(event, RequestEvent):
            await self._dispatch_request(event)
        elif isinstance(event, MetaEvent):
            await self._dispatch_meta(event)
        elif isinstance(event, UnknownEvent):
            logger.debug(f"[Handler] 未知事件: {event.raw.get('post_type', '?')}")

    async def _dispatch_message(self, event: MessageEvent) -> None:
        """
        分发消息事件（群消息 + 私聊）。
        通过 _MixinProxy 调用各 Mixin 自身定义的 mixin_on_message。
        """
        # Mixin 消息钩子
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_message
            if not method:
                continue
            try:
                await method(event)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_message 错误: {e}")

        # Extension 消息钩子（统一入口）
        for ext in self.extensions.values():
            if not getattr(ext, "mixin_enabled", True):
                continue
            try:
                await ext.ext_on_message(event)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_message 错误: {e}")

        # 群消息快捷钩子
        if isinstance(event, GroupMessageEvent):
            for ext in self.extensions.values():
                if not getattr(ext, "mixin_enabled", True):
                    continue
                try:
                    await ext.ext_on_group_message(event)
                except Exception as e:
                    logger.error(f"[Handler] Extension {ext.ext_name} on_group_message 错误: {e}")

        # 私聊快捷钩子
        if isinstance(event, PrivateMessageEvent):
            for ext in self.extensions.values():
                if not getattr(ext, "mixin_enabled", True):
                    continue
                try:
                    await ext.ext_on_private_message(event)
                except Exception as e:
                    logger.error(f"[Handler] Extension {ext.ext_name} on_private_message 错误: {e}")

    async def _dispatch_notice(self, event: NoticeEvent) -> None:
        """
        分发通知事件（群禁言/退群/入群等）。
        """
        # Mixin 通知钩子
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_notice
            if not method:
                continue
            try:
                await method(event)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_notice 错误: {e}")

        # Extension 通知钩子
        for ext in self.extensions.values():
            if not getattr(ext, "mixin_enabled", True):
                continue
            try:
                await ext.ext_on_notice(event)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_notice 错误: {e}")

    async def _dispatch_request(self, event: RequestEvent) -> None:
        """
        分发请求事件（加好友/加群请求）。
        """
        # Mixin 请求钩子
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_request
            if not method:
                continue
            try:
                await method(event)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_request 错误: {e}")

        # Extension 请求钩子
        for ext in self.extensions.values():
            if not getattr(ext, "mixin_enabled", True):
                continue
            try:
                await ext.ext_on_request(event)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_request 错误: {e}")

    async def _dispatch_meta(self, event: MetaEvent) -> None:
        """
        分发元事件（心跳/生命周期）。
        """
        # Mixin 元事件钩子
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_meta
            if not method:
                continue
            try:
                await method(event)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_meta 错误: {e}")

        # Extension 元事件钩子
        for ext in self.extensions.values():
            if not getattr(ext, "mixin_enabled", True):
                continue
            try:
                await ext.ext_on_meta(event)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_meta 错误: {e}")

    # ═══════════════════════════════════════════════════
    # Action 响应处理
    # ═══════════════════════════════════════════════════

    async def handle_response(self, response: ActionResponse) -> None:
        """
        处理 Action 回包（echo 配对后的回调）。
        """
        # Mixin 响应钩子
        for proxy in self._mixin_proxies:
            method = proxy.mixin_on_response
            if not method:
                continue
            try:
                await method(response)
            except Exception as e:
                logger.error(f"[Handler] Mixin {proxy.mixin_name} on_response 错误: {e}")

        # Extension 响应钩子
        for ext in self.extensions.values():
            if not getattr(ext, "mixin_enabled", True):
                continue
            try:
                await ext.ext_on_response(response)
            except Exception as e:
                logger.error(f"[Handler] Extension {ext.ext_name} on_response 错误: {e}")

    # ═══════════════════════════════════════════════════
    # 确认管理
    # ═══════════════════════════════════════════════════

    async def submit_sensitive_action(
        self,
        action_type: str,
        params: dict,
        description: str,
        executor: int = 0,
    ) -> str:
        """
        提交敏感操作（退群/踢人/禁言等）到确认队列。
        返回 token。
        """
        token = await self.confirm_manager.submit(
            action_type=action_type,
            params=params,
            description=description,
            executor=executor,
        )
        logger.warning(f"[Handler] 敏感操作待审批 | token={token} desc={description}")
        return token

    async def approve_action(self, token: str, admin_id: int = 0) -> tuple[bool, str]:
        """管理员批准敏感操作。"""
        ok, msg = await self.confirm_manager.approve(token, admin_id)
        if ok and self.client:
            # 批准后执行对应的 Action
            req = self.confirm_manager.get(token)
            if req:
                await self._execute_approved_action(req)
        return ok, msg

    async def reject_action(self, token: str, admin_id: int = 0) -> tuple[bool, str]:
        """管理员拒绝敏感操作。"""
        return await self.confirm_manager.reject(token, admin_id)

    async def _execute_approved_action(self, req) -> None:
        """执行已批准的敏感操作。"""
        from .actions import (
            SetGroupBanAction,
            SetGroupKickAction,
            SetGroupLeaveAction,
            SetGroupWholeBanAction,
        )

        action_type = req.action_type
        params = req.params

        action_map = {
            "set_group_leave": SetGroupLeaveAction,
            "set_group_kick": SetGroupKickAction,
            "set_group_ban": SetGroupBanAction,
            "set_group_whole_ban": SetGroupWholeBanAction,
        }

        action_class = action_map.get(action_type)
        if not action_class:
            logger.error(f"[Handler] 未知敏感操作类型: {action_type}")
            return

        action = action_class(**params)
        if self.client:
            resp = await self.client.call(action)
            logger.info(f"[Handler] 执行 {action_type}: " f"{'成功' if resp.ok else '失败'} ({resp.retcode})")

    # ═══════════════════════════════════════════════════
    # 管理员检查
    # ═══════════════════════════════════════════════════

    def is_admin(self, user_id: int) -> bool:
        """检查是否为管理员。"""
        return user_id in self.config.admin_qq

    # ═══════════════════════════════════════════════════
    # 关闭
    # ═══════════════════════════════════════════════════

    async def shutdown(self) -> None:
        """优雅关闭。"""
        logger.info("[Handler] 开始关闭流程...")

        # 关闭 Extension
        for name in list(self.extensions.keys()):
            ext = self.extensions[name]
            try:
                await ext.ext_unload()
            except Exception as e:
                logger.error(f"[Handler] Extension {name} unload 错误: {e}")
        self.extensions.clear()

        # 关闭 Mixin
        await self._teardown_mixins()

        # 关闭 Client
        if self.client and not self.client.is_closed:
            await self.client.close()

        logger.info("[Handler] 关闭完成")


# ═══════════════════════════════════════════════════════════
# 动态 Mixin 组合工厂
# ═══════════════════════════════════════════════════════════


def create_handler_class(mixin_classes: List[Type[BaseMixin]]) -> Type[OneBotHandler]:
    """
    动态创建 Handler 类，将 Mixin 列表通过多重继承组合。
    这是实现「Mixin 也能被 Mixin」的关键：
    每个 Mixin 本身可以继承其他 Mixin，
    最终通过 MRO 线性化后由 Handler 统一继承。
    """
    # 去重并保留顺序
    seen: set = set()
    unique_mixins: List[Type[BaseMixin]] = []
    for m in mixin_classes:
        if m not in seen and m is not BaseMixin:
            seen.add(m)
            unique_mixins.append(m)

    # 动态创建类
    class_name = "DynamicOneBotHandler"
    bases = tuple(unique_mixins) + (OneBotHandler,)

    cls = type(class_name, bases, {})
    return cls


# ═══════════════════════════════════════════════════════════
# Mixin 代理对象
# ═══════════════════════════════════════════════════════════


class _MixinProxy:
    """
    Mixin 代理对象。

    每个代理绑定到一个具体的 Mixin 类，只暴露该类自身定义的方法。
    这样在事件分发时，调用 proxy.mixin_on_message()
    只会触发该 Mixin 自己的实现，不会重复触发其他 Mixin。

    属性访问规则：
      - 先查 cls.__dict__（该 Mixin 自身定义的方法/属性）
      - 再 fallback 到 handler 上的同名属性（用于共享状态）

    关键修复：
      绑定方法时必须用 types.MethodType 直接从当前 Mixin 类绑定到
      handler，不能走 getattr(handler, name)（会沿 MRO 找到排在前面
      的 Mixin 的同名方法，导致覆盖）。
    """

    def __init__(self, mixin_cls: Type[BaseMixin], handler: Any):
        import types

        self._cls = mixin_cls
        self._handler = handler

        # 从类自身定义中收集可调用方法，直接绑定到 handler
        self._own_methods: Dict[str, Any] = {}
        for name, val in mixin_cls.__dict__.items():
            if callable(val) and not name.startswith("__"):
                # 关键：用 types.MethodType 直接从当前 Mixin 类绑定
                # 避免 getattr(handler, name) 走 MRO 被前面的 Mixin 覆盖
                bound = types.MethodType(val, handler)
                self._own_methods[name] = bound

    @property
    def mixin_name(self) -> str:
        """Mixin 名称。"""
        return getattr(self._cls, "mixin_name", self._cls.__name__.lower())

    @property
    def mixin_priority(self) -> int:
        """Mixin 优先级（数字小=先执行）。"""
        return getattr(self._cls, "mixin_priority", 100)

    @property
    def mixin_enabled(self) -> bool:
        """Mixin 是否启用。"""
        return getattr(self._cls, "mixin_enabled", True)

    def __getattr__(self, name: str) -> Any:
        """
        属性访问：
        1. 优先返回该 Mixin 自身定义的方法
        2. fallback 到 handler 的同名属性（共享状态）
        """
        if name in self._own_methods:
            return self._own_methods[name]
        # Fallback: 从 handler 获取（如 config, logger 等共享资源）
        return getattr(self._handler, name)

    def __repr__(self) -> str:
        return f"<MixinProxy {self._cls.__name__} " f"name={self.mixin_name} " f"priority={self.mixin_priority}>"


def get_mixin_instances_from_handler(handler: Any) -> List[Any]:
    """
    从 Handler 实例中提取所有 Mixin 代理对象（按优先级排序）。
    """
    results: List[Any] = []
    seen: Set[type] = set()

    for cls in handler.__class__.__mro__:
        if cls is BaseMixin or not issubclass(cls, BaseMixin):
            continue
        if cls in seen:
            continue
        seen.add(cls)

        # 排除动态 Handler 类自身
        if cls.__module__ == __name__:
            continue

        results.append(_MixinProxy(cls, handler))

    results.sort(key=lambda p: p.mixin_priority)
    return results
