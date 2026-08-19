"""
OneBot 11 Server — 主入口
============================

运行方式:
    python main.py
    python main.py --host 0.0.0.0 --port 8080 --token mysecret
    python -m onebot_server.server --admin 123456 --admin 789012

LLOneBot 反向 WS 地址填: ws://127.0.0.1:8765
"""

import os
import sys

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from onebot_server.server import OneBotServer
from onebot_server.handler import OneBotHandler
from onebot_server.events import GroupMessageEvent, PrivateMessageEvent
from onebot_server.actions import SendPrivateMsgAction
from onebot_server.segments import build_message


class MyBot(OneBotHandler):
    """
    内置 handler —— 用于全局兜底逻辑。
    具体的业务功能建议写在 extensions/ 里，可以热加载。
    """

    async def on_connect(self, client):
        """连接建立时的全局处理。"""
        print(f"✅ Bot connected! self_id={client.self_id}")

    async def on_group_message(self, event: GroupMessageEvent, client):
        """
        全局兜底：如果消息没有被任何 extension 处理，
        在这里做最后的响应（可选）。
        """
        pass  # extensions 会处理，这里留空

    async def on_private_message(self, event: PrivateMessageEvent, client):
        """私聊兜底"""
        if "你好" in event.get_text():
            await client.send(
                SendPrivateMsgAction(
                    user_id=event.user_id,
                    message=build_message("你好！我是机器人，输入 /help 查看命令。"),
                )
            )


def create_server() -> OneBotServer:
    """创建并配置服务器实例"""
    import argparse

    parser = argparse.ArgumentParser(description="OneBot 11 Server")
    parser.add_argument("--config", "-c", default="config.toml", help="TOML 配置文件路径")
    parser.add_argument("--host", default=None, help="覆盖配置中的 server.host")
    parser.add_argument("--port", type=int, default=None, help="覆盖配置中的 server.port")
    parser.add_argument("--token", default=None, help="覆盖配置中的 server.access_token")
    parser.add_argument("--admin", type=int, action="append", default=[], help="添加管理员 QQ 号（可多次使用）")
    parser.add_argument("--no-hot-reload", action="store_true", help="禁用插件热重载")
    parser.add_argument(
        "--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="覆盖配置中的日志级别"
    )
    args = parser.parse_args()

    # 加载配置
    from onebot_server.config import get_config

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

    # 配置 loguru
    from loguru import logger as _log

    _log.remove()
    _log.add(
        sys.stderr,
        level=args.log_level or config.log_level,
        format="<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <7}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - {message}",
        colorize=True,
    )
    log_dir = config.log_dir
    os.makedirs(log_dir, exist_ok=True)
    _log.add(
        os.path.join(log_dir, "onebot_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        rotation=f"{config.log_max_size} MB",
        retention=config.log_retention,
        encoding="utf-8",
    )

    # 打印启动横幅
    print("""
╔══════════════════════════════════════════╗
║     OneBot 11 Server  v2.0.0               ║
║     Hot-reloadable · Loguru · Safe         ║
╚══════════════════════════════════════════╝
    """)

    # 创建服务器
    server = OneBotServer(
        config_path=args.config,
        handler_class=None,  # 使用默认动态 Handler
        mixin_classes=None,  # 从配置加载
    )
    return server


if __name__ == "__main__":
    server = create_server()
    server.run_forever()
