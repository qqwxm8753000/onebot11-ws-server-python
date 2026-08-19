"""
server.py — WebSocket 服务器
==========================================
整合所有组件：
  - 加载 TOML 配置
  - 初始化 Mixin（动态组合到 Handler）
  - 初始化 Extension Manager
  - 启动 WebSocket 服务
  - 处理连接/断连/消息
  - CLI 命令行入口
"""

from __future__ import annotations

import asyncio
import importlib
import json
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import websockets
from websockets.server import WebSocketServerProtocol

from .client import OneBotClient
from .config import Config, get_config
from .confirm import ConfirmManager
from .extension_manager import ExtensionManager
from .handler import (
    OneBotHandler,
    create_handler_class,
)
from .logger import get_logger, init_logger
from .mixin.backup_mixin import BackupMixin
from .mixin.console_mixin import ConsoleMixin

# 内置 Mixin 导入
from .mixin.log_mixin import LogMixin
from .mixin.task_mixin import TaskMixin
from .mixin_base import BaseMixin
from .whitelist import WhitelistManager

logger = get_logger()


class OneBotServer:
    """
    OneBot WebSocket 服务器。
    启动方式:
      server = OneBotServer(config_path="config.toml")
      server.run_forever()
    """

    def __init__(
        self,
        config_path: str = "config.toml",
        handler_class: Optional[Type[OneBotHandler]] = None,
        mixin_classes: Optional[List[Type[BaseMixin]]] = None,
    ):
        # 加载配置
        self.config_path: str = config_path
        self.config: Config = get_config(config_path)

        # 初始化日志
        init_logger(
            level=self.config.log_level,
            log_dir=self.config.log_dir,
            console=self.config.log_console,
            max_size=self.config.log_max_size,
            retention=self.config.log_retention,
        )
        self.logger = get_logger()

        # 确认管理器
        self.confirm_manager: ConfirmManager = ConfirmManager(timeout=self.config.confirm_timeout)

        # 白名单管理器
        self.whitelist: WhitelistManager = WhitelistManager(data_dir="data")

        # Mixin 列表（默认包含内置 Mixin）
        if mixin_classes is None:
            mixin_classes = self._load_mixin_list()
        self._mixin_classes: List[Type[BaseMixin]] = mixin_classes

        # 动态创建 Handler 类
        if handler_class is None:
            handler_class = create_handler_class(self._mixin_classes)
        self._handler_class: Type[OneBotHandler] = handler_class

        # 创建 Handler 实例
        self.handler: OneBotHandler = self._handler_class(
            config=self.config,
            whitelist=self.whitelist,
            confirm_manager=self.confirm_manager,
        )

        # Extension 管理器
        self.extension_manager: ExtensionManager = ExtensionManager(
            ext_dir=self.config.ext_dir,
            handler=self.handler,
            watch_interval=self.config.watch_interval,
            ext_suffix=self.config.ext_suffix,
        )
        self.handler.extension_manager = self.extension_manager

        # WebSocket 服务器引用
        self._server: Optional[Any] = None
        self._serving: bool = False

        # 当前客户端引用
        self._client: Optional[OneBotClient] = None

        self.logger.info("=" * 50)
        self.logger.info("  OneBot 11 Server 初始化完成")
        self.logger.info(f"  监听: {self.config.server_host}:{self.config.server_port}")
        self.logger.info(f"  Mixin: {len(self._mixin_classes)} 个")
        self.logger.info(f"  插件目录: {self.config.ext_dir}")
        self.logger.info("=" * 50)

    # ─── Mixin 加载 ────────────────────────────────

    def _load_mixin_list(self) -> List[Type[BaseMixin]]:
        """
        根据配置文件加载 Mixin 类列表。
        内置 Mixin 映射：
          log → LogMixin
          backup → BackupMixin
          console → ConsoleMixin
          task → TaskMixin
        也可从 mixin/ 目录动态加载自定义 Mixin。
        """
        builtin_map: Dict[str, Type[BaseMixin]] = {
            "log": LogMixin,
            "backup": BackupMixin,
            "console": ConsoleMixin,
            "task": TaskMixin,
        }

        mixin_names = self.config.auto_load_mixins
        result: List[Type[BaseMixin]] = []

        for name in mixin_names:
            name = name.lower().strip()
            if name in builtin_map:
                result.append(builtin_map[name])
            else:
                # 尝试从 mixin/ 目录动态加载
                loaded = self._load_custom_mixin(name)
                if loaded:
                    result.append(loaded)
                else:
                    self.logger.warning(f"[Server] 未找到 Mixin: {name}")

        return result

    def _load_custom_mixin(self, name: str) -> Optional[Type[BaseMixin]]:
        """
        从 mixin/ 目录动态加载自定义 Mixin。
        使用 importlib.import_module 走包路径，确保模块内的
        相对导入（from .xxx）能正确解析到 onebot_server 包。
        """
        # 计算包内模块路径，例如 "onebot_server.mixin.my_mixin"
        mixin_dir = Path(self.config.mixin_dir)
        try:
            # mixin_dir 通常是 .../onebot_server/mixin
            # 取其父目录加入 sys.path 不优雅，改用包路径推导
            # 找到 onebot_server 包的路径
            pkg_parent = mixin_dir.parent
            if str(pkg_parent) not in sys.path:
                sys.path.insert(0, str(pkg_parent))
            module_fullname = f"onebot_server.mixin.{name}"

            # 若已加载过，先移除缓存再重新加载
            if module_fullname in sys.modules:
                del sys.modules[module_fullname]

            module = importlib.import_module(module_fullname)

            # 查找 BaseMixin 子类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseMixin) and attr is not BaseMixin:
                    self.logger.info(f"[Server] 加载自定义 Mixin: {attr.__name__}")
                    return attr
        except Exception as e:
            self.logger.error(f"[Server] 加载 Mixin {name} 失败: {e}")

        return None

    # ─── WebSocket 服务 ──────────────────────────────

    async def start(self) -> None:
        """启动服务器（异步入口）。"""
        host = self.config.server_host
        port = self.config.server_port
        path = self.config.server_path

        self.logger.info(f"[Server] 启动 WebSocket 服务 ws://{host}:{port}{path}")

        # 冷加载 Extension
        loaded = await self.extension_manager.cold_load_all()
        self.logger.info(f"[Server] 冷加载插件: {loaded} 个")

        # 启动文件监控
        if self.config.hot_reload:
            await self.extension_manager.start_watcher()

        # 启动确认清理任务
        self._cleanup_task = asyncio.create_task(self.confirm_manager.cleanup_task(60))

        # 启动 WebSocket 服务器
        self._serving = True
        async with websockets.serve(
            self._handle_connection,
            host,
            port,
            ping_interval=20,
            ping_timeout=10,
        ):
            self.logger.info("[Server] WebSocket 服务已就绪，等待 LLOneBot 连接...")
            # 保持运行直到收到停止信号
            stop_event = asyncio.Event()
            self._stop_event = stop_event

            # 注册信号处理器（get_running_loop 兼容 3.12+）
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._on_shutdown(s)))
                except NotImplementedError:
                    # Windows 不支持 add_signal_handler
                    pass

            await stop_event.wait()

    async def _on_shutdown(self, sig: signal.Signals) -> None:
        """收到停止信号时的处理。"""
        self.logger.info(f"[Server] 收到信号 {sig.name}，开始关闭...")
        self._serving = False
        if hasattr(self, "_stop_event"):
            self._stop_event.set()

    async def _handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """
        处理一条 WebSocket 连接。
        LLOneBot 作为客户端连入，这里是服务端。
        """
        peer = websocket.remote_address
        self.logger.info(f"[Server] 新连接来自 {peer}")

        # Token 鉴权
        if not self._check_auth(websocket):
            self.logger.warning(f"[Server] 鉴权失败，关闭连接 {peer}")
            await websocket.close(code=1008, reason="Unauthorized")
            return

        # 创建 Client 对象
        client = OneBotClient(
            websocket=websocket,
            action_timeout=self.config.action_timeout,
        )
        self._client = client
        self.handler.client = client

        # 通知 Handler 连接建立
        await self.handler.attach_client(client)

        try:
            # 持续读取消息
            async for raw in websocket:
                await self._process_message(client, raw)
        except websockets.ConnectionClosed as e:
            self.logger.info(f"[Server] 连接关闭: {e.code} {e.reason}")
        except Exception as e:
            self.logger.error(f"[Server] 连接异常: {e}")
        finally:
            # 清理
            await self.handler.detach_client(client)
            if self._client is client:
                self._client = None
            self.logger.info(f"[Server] 连接已清理 {peer}")

    def _check_auth(self, websocket: WebSocketServerProtocol) -> bool:
        """验证 WebSocket 握手的 Authorization 头。"""
        token = self.config.access_token
        if not token:
            return True  # 未配置 token 则跳过鉴权

        # 从请求头获取 token
        headers = getattr(websocket, "request_headers", None)
        if headers is None:
            headers = getattr(websocket, "headers", None)

        if headers is None:
            self.logger.warning("[Server] 无法获取请求头，跳过鉴权")
            return True

        auth_header = ""
        if isinstance(headers, dict):
            auth_header = headers.get("authorization", "")
        else:
            try:
                auth_header = headers.get("Authorization", "")
            except Exception:
                pass

        if not auth_header:
            self.logger.warning("[Server] 缺少 Authorization 头")
            return False

        # 支持 "Bearer <token>" 格式
        expected = f"Bearer {token}"
        if auth_header == expected:
            return True

        # 也支持直接传 token
        if auth_header == token:
            return True

        self.logger.warning("[Server] Token 不匹配")
        return False

    async def _process_message(self, client: OneBotClient, raw: str) -> None:
        """处理一条收到的消息（可能是事件也可能是响应）。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.logger.warning(f"[Server] 非 JSON 数据: {raw[:200]}")
            return

        # 判断是事件还是 Action 响应
        post_type = data.get("post_type")
        echo = data.get("echo")

        if post_type:
            # 是事件推送
            await self.handler.handle_event(data)
        elif echo is not None:
            # 是 Action 响应
            from .actions import ActionResponse

            resp = ActionResponse.from_dict(data)
            await client.handle_response(raw)
            await self.handler.handle_response(resp)
        else:
            self.logger.debug(f"[Server] 未知消息类型: {str(data)[:200]}")

    # ─── 运行控制 ────────────────────────────────

    def run_forever(self) -> None:
        """同步入口：启动并阻塞直到退出。"""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            self.logger.info("[Server] 用户中断 (Ctrl+C)")
        finally:
            # 确保清理
            asyncio.run(self._shutdown())

    async def _shutdown(self) -> None:
        """关闭流程。"""
        self.logger.info("[Server] 执行关闭流程...")

        # 停止文件监控
        await self.extension_manager.stop_watcher()

        # 冷卸载所有 Extension
        await self.extension_manager.cold_unload_all()

        # 关闭 Handler
        await self.handler.shutdown()

        # 关闭确认清理任务
        if hasattr(self, "_cleanup_task") and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        self.logger.info("[Server] 完全关闭")


# ═══════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════


def main():
    """命令行入口: python -m onebot_server.server [选项]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="OneBot 11 WebSocket Server — 自写 QQ 机器人后端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m onebot_server.server                    # 使用默认 config.toml
  python -m onebot_server.server -c my_config.toml  # 指定配置文件
  python -m onebot_server.server --host 0.0.0.0 --port 9000
  python -m onebot_server.server --token my-secret-token
  python -m onebot_server.server --admin 123456789

运行后控制台可用命令:
  help      显示帮助
  status    查看状态
  pending   查看待审批
  approve <token>   批准
  reject  <token>   拒绝
  send <gid> <text> 发消息
  leave <gid>       退群（需确认）
  wl-list           列白名单
  backup            手动备份
  ext-list          列插件
  ext-hot load <n>  热加载插件
  ext-hot unload <n> 热卸载插件
  quit              退出
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        default="config.toml",
        help="TOML 配置文件路径（默认: config.toml）",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="覆盖配置中的 server.host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="覆盖配置中的 server.port",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="覆盖配置中的 server.access_token",
    )
    parser.add_argument(
        "--admin",
        type=int,
        action="append",
        default=None,
        help="添加管理员 QQ 号（可多次使用）",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="覆盖配置中的日志级别",
    )
    parser.add_argument(
        "--no-hot-reload",
        action="store_true",
        help="禁用插件热重载",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="OneBot Server 2.0.0",
    )

    args = parser.parse_args()

    # 加载配置
    config = get_config(args.config)

    # 命令行覆盖
    if args.host:
        config.set("server.host", args.host)
    if args.port:
        config.set("server.port", args.port)
    if args.token:
        config.set("server.access_token", args.token)
    if args.admin:
        current = list(config.admin_qq)
        for qq in args.admin:
            if qq not in current:
                current.append(qq)
        config.set("admin.admin_qq", current)
    if args.log_level:
        config.set("logging.level", args.log_level)
    if args.no_hot_reload:
        config.set("extension.hot_reload", False)

    # 启动服务器
    server = OneBotServer(config_path=args.config)
    server.run_forever()


if __name__ == "__main__":
    main()
