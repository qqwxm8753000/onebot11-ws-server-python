"""
extension_base.py — Extension 基类
==========================================
所有插件必须继承 BaseExtension。
Extension 只能继承 Mixin，不能直接操作 WebSocket 连接。
通过 handler 和 client 属性间接与 LLOneBot 交互。
"""

from __future__ import annotations

from typing import Any

from .logger import get_logger
from .mixin_base import BaseMixin

logger = get_logger()


class BaseExtension(BaseMixin):
    """
    Extension 基类。所有用户插件继承此类。

    与 Mixin 的区别：
    - Extension 可以被热加载/热卸载/冷加载/冷卸载
    - Extension 只能继承 Mixin，不能直接触碰 WebSocket
    - Extension 通过 self.handler 和 self.client 访问核心功能

    生命周期（由 ExtensionManager 驱动）：
      - ext_load(handler)      加载时调用（只一次）
      - ext_on_connect(client)  连接建立时
      - ext_on_message(event)   消息事件
      - ext_on_notice(event)    通知事件
      - ext_on_request(event)   请求事件
      - ext_on_meta(event)      元事件
      - ext_on_response(resp)   Action 回包
      - ext_unload()           卸载时清理

    属性：
      - handler: OneBotHandler 引用
      - client:  OneBotClient 引用（可能为 None）
      - enabled: 是否启用
      - priority: 执行优先级（数字小=先执行）
      - description: 插件描述
    """

    # ─── 类属性（子类覆盖）──────────────────────────────
    # 插件名称（默认从类名推导）
    ext_name: str = ""
    # 插件描述
    description: str = ""
    # 优先级（数字小=先执行）
    priority: int = 100
    # 版本号
    version: str = "1.0.0"

    def __init_subclass__(cls, **kwargs):
        """子类注册。"""
        super().__init_subclass__(**kwargs)
        if not cls.ext_name and cls is not BaseExtension:
            # 自动推导名称
            name = cls.__name__.lower()
            if name.endswith("extension"):
                name = name[:-9]
            cls.ext_name = name

    # ─── 核心引用 ──────────────────────────────────────

    @property
    def handler(self) -> Any:
        """获取 Handler 引用（延迟绑定）。"""
        return getattr(self, "_handler", None)

    @handler.setter
    def handler(self, value: Any) -> None:
        self._handler = value

    @property
    def client(self) -> Any:
        """获取 Client 引用（延迟绑定）。"""
        h = self.handler
        if h:
            return getattr(h, "client", None)
        return getattr(self, "_client", None)

    @client.setter
    def client(self, value: Any) -> None:
        self._client = value

    # ─── 生命周期：加载 ─────────────────────────────────

    async def ext_load(self, handler: Any) -> bool:
        """
        插件加载钩子。返回 True 表示加载成功。
        子类可重写此方法进行初始化。
        """
        self._handler = handler
        self._client = getattr(handler, "client", None)
        logger.info(f"[Extension] 加载: {self.ext_name} " f"v{self.version} — {self.description}")
        return True

    # ─── 生命周期：连接 ─────────────────────────────────

    async def ext_on_connect(self, client: Any) -> None:
        """WebSocket 连接建立后调用。"""
        self._client = client

    async def ext_on_disconnect(self, client: Any) -> None:
        """WebSocket 连接断开后调用。"""
        pass

    # ─── 生命周期：事件 ─────────────────────────────────

    async def ext_on_event(self, event: Any) -> None:
        """所有事件的统一入口。"""
        pass

    async def ext_on_message(self, event: Any) -> None:
        """消息事件。"""
        pass

    async def ext_on_group_message(self, event: Any) -> None:
        """群消息事件（快捷钩子）。"""
        pass

    async def ext_on_private_message(self, event: Any) -> None:
        """私聊消息事件（快捷钩子）。"""
        pass

    async def ext_on_notice(self, event: Any) -> None:
        """通知事件。"""
        pass

    async def ext_on_request(self, event: Any) -> None:
        """请求事件。"""
        pass

    async def ext_on_meta(self, event: Any) -> None:
        """元事件。"""
        pass

    async def ext_on_response(self, response: Any) -> None:
        """Action 响应回包。"""
        pass

    # ─── 生命周期：卸载 ─────────────────────────────────

    async def ext_unload(self) -> bool:
        """
        插件卸载钩子。返回 True 表示卸载成功。
        子类可重写此方法进行清理（关闭文件、取消任务等）。
        """
        logger.info(f"[Extension] 卸载: {self.ext_name}")
        return True

    # ─── 工具方法（Extension 可用的安全接口）───────────

    async def safe_send_group_msg(self, group_id: int, message: list) -> Any:
        """安全地发送群消息（通过 client）。"""
        client = self.client
        if not client:
            logger.warning(f"[Extension:{self.ext_name}] client 未就绪，无法发消息")
            return None
        return await client.send_group_msg(group_id=group_id, message=message)

    async def safe_send_private_msg(self, user_id: int, message: list) -> Any:
        """安全地发送私聊消息。"""
        client = self.client
        if not client:
            return None
        return await client.send_private_msg(user_id=user_id, message=message)

    def get_config(self, key: str, default: Any = None) -> Any:
        """从 handler 获取配置值。"""
        h = self.handler
        if h and hasattr(h, "config"):
            return h.config.get(key, default)
        return default

    def is_admin(self, user_id: int) -> bool:
        """检查某 QQ 号是否为管理员。"""
        h = self.handler
        if h and hasattr(h, "is_admin"):
            return h.is_admin(user_id)
        return False

    # ─── 错误兜底 ───────────────────────────────────────

    async def _on_error(self, exc: Exception, source, args: tuple, kwargs: dict) -> None:
        logger.error(f"[Extension:{self.ext_name}] 错误: {exc}")

    # ─── 字符串表示 ─────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<Extension name={self.ext_name} "
            f"v{self.version} "
            f"priority={self.priority} "
            f"enabled={getattr(self, 'mixin_enabled', True)}>"
        )
