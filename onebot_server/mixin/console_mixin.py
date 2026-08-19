"""
console_mixin.py — 控制台 Mixin
==========================================
提供交互式命令行，支持：
  - 查看/审批待确认请求
  - 发送消息/禁言/踢人
  - 加载/卸载/重载 Extension
  - 查看运行状态
  - 退群确认
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple

from ..actions import text_segment  # noqa: F401
from ..confirm import ConfirmManager
from ..logger import get_logger
from ..mixin_base import BaseMixin
from ..whitelist import WhitelistManager

logger = get_logger()


class ConsoleMixin(BaseMixin):
    """
    控制台 Mixin：
    - 在终端提供交互式命令
    - 处理退群确认、敏感操作审批
    - 可被其他 Mixin 继承扩展命令
    """

    mixin_name: str = "console"
    mixin_priority: int = 10

    def __init__(
        self,
        prompt: str = "onebot> ",
        confirm_manager: Optional[ConfirmManager] = None,
        whitelist: Optional[WhitelistManager] = None,
        **kwargs,
    ):
        self.prompt: str = prompt
        self._confirm = confirm_manager
        self._whitelist = whitelist
        self._handler: Any = None
        self._client: Any = None
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        # 命令注册表（子类可扩展）
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._register_builtin_commands()
        super().__init__(**kwargs)

    # ─── 初始化 ──────────────────────────────────────────

    async def mixin_setup(self, handler: Any) -> None:
        """获取 handler 引用，启动控制台任务。"""
        self._handler = handler
        self._client = getattr(handler, "client", None)

        # 从 handler 获取依赖
        if self._confirm is None:
            self._confirm = getattr(handler, "confirm_manager", None)
        if self._whitelist is None:
            self._whitelist = getattr(handler, "whitelist", None)

        self._running = True
        # 在事件循环中启动控制台（get_running_loop 兼容 3.12+）
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run_console())
        logger.info("[ConsoleMixin] 交互式控制台已启动")

    def _register_builtin_commands(self) -> None:
        """注册内置命令。"""
        self._commands = {
            "help": {"func": self._cmd_help, "desc": "显示帮助信息"},
            "status": {"func": self._cmd_status, "desc": "查看运行状态"},
            "pending": {"func": self._cmd_pending, "desc": "查看待审批请求"},
            "approve": {"func": self._cmd_approve, "desc": "批准请求: approve <token>"},
            "reject": {"func": self._cmd_reject, "desc": "拒绝请求: reject <token>"},
            "send": {"func": self._cmd_send, "desc": "发群消息: send <group_id> <text>"},
            "ban": {"func": self._cmd_ban, "desc": "禁言: ban <group_id> <user_id> [duration]"},
            "kick": {"func": self._cmd_kick, "desc": "踢人: kick <group_id> <user_id>"},
            "leave": {"func": self._cmd_leave, "desc": "退群（需确认）: leave <group_id>"},
            "wl-add": {"func": self._cmd_wl_add, "desc": "加白名单: wl-add <group_id>"},
            "wl-rm": {"func": self._cmd_wl_rm, "desc": "删白名单: wl-rm <group_id>"},
            "wl-list": {"func": self._cmd_wl_list, "desc": "列白名单"},
            "backup": {"func": self._cmd_backup, "desc": "手动备份白名单"},
            "ext-list": {"func": self._cmd_ext_list, "desc": "列出已加载插件"},
            "ext-reload": {"func": self._cmd_ext_reload, "desc": "重载插件: ext-reload <name>"},
            "ext-hot": {"func": self._cmd_ext_hot, "desc": "热加载/卸载: ext-hot <load|unload> <name>"},
            "quit": {"func": self._cmd_quit, "desc": "退出程序"},
        }

    def register_command(self, name: str, func, desc: str = "") -> None:
        """扩展命令注册接口（子类或 Extension 可调用）。"""
        self._commands[name] = {"func": func, "desc": desc}

    # ─── 控制台主循环 ────────────────────────────────────

    async def _run_console(self) -> None:
        """控制台主循环，在 asyncio 中运行。"""
        loop = asyncio.get_running_loop()
        print()
        print("=" * 50)
        print("  OneBot 11 Server — 交互式控制台")
        print("  输入 'help' 查看命令，'quit' 退出")
        print("=" * 50)

        while self._running:
            try:
                # 在线程池中读取输入（不阻塞事件循环）
                line = await loop.run_in_executor(None, self._read_input)
                if line is None:
                    break
                line = line.strip()
                if not line:
                    continue

                await self._dispatch_command(line)

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                print(f"[错误] {e}")

        print("\n[控制台] 已退出")

    def _read_input(self) -> Optional[str]:
        """同步读取一行输入。"""
        try:
            return input(self.prompt)
        except (KeyboardInterrupt, EOFError):
            return None

    async def _dispatch_command(self, line: str) -> None:
        """解析并执行命令。"""
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        handler = self._commands.get(cmd)
        if not handler:
            print(f"未知命令: {cmd}，输入 'help' 查看可用命令")
            return

        func = handler["func"]
        try:
            # 所有命令函数都声明为 async，统一 await
            # 不用 isawaitable：传错类型会立刻 TypeError，便于排查
            await func(*args)
        except Exception as e:
            print(f"[命令错误] {e}")

    # ─── 内置命令实现 ────────────────────────────────────

    async def _cmd_help(self, *args) -> None:
        """显示帮助。"""
        print("\n可用命令:")
        print("-" * 50)
        for name, info in sorted(self._commands.items()):
            desc = info.get("desc", "")
            print(f"  {name:<12} — {desc}")
        print("-" * 50)

    async def _cmd_status(self, *args) -> None:
        """查看运行状态。"""
        handler = self._handler
        if not handler:
            print("Handler 未就绪")
            return

        client = self._client
        conn_status = "已连接" if client and not client.is_closed else "未连接"
        uptime = getattr(client, "uptime", 0)
        self_id = getattr(handler, "self_id", 0)

        print(f"\n{'='*40}")
        print(f"  连接状态:  {conn_status}")
        print(f"  QQ 号:    {self_id}")
        print(f"  运行时间:  {uptime:.0f}s")
        if self._confirm:
            pending = await self._confirm.list_pending()
            print(f"  待审批:   {len(pending)} 条")
        if self._whitelist:
            wl_count = len(self._whitelist.list_groups())
            print(f"  白名单群: {wl_count} 个")
        ext_count = len(getattr(handler, "extensions", {}))
        print(f"  已加载插件: {ext_count} 个")
        print(f"{'='*40}")

    async def _cmd_pending(self, *args) -> None:
        """查看待审批请求。"""
        if not self._confirm:
            print("确认管理器未初始化")
            return

        pending = await self._confirm.list_pending()
        if not pending:
            print("当前没有待审批的请求")
            return

        print(f"\n{'令牌':<20} {'类型':<15} {'描述':<30} {'剩余':<8}")
        print("-" * 80)
        for req in pending:
            print(f"{req['token']:<20} {req['action_type']:<15} " f"{req['description']:<30} {req['expires_in']}s")

    async def _cmd_approve(self, *args) -> None:
        """批准请求: approve <token>"""
        if not args:
            print("用法: approve <token>")
            return
        token = args[0]
        if not self._confirm:
            print("确认管理器未初始化")
            return
        ok, msg = await self._confirm.approve(token)
        print(f"{'✓' if ok else '✗'} {msg}")

    async def _cmd_reject(self, *args) -> None:
        """拒绝请求: reject <token>"""
        if not args:
            print("用法: reject <token>")
            return
        token = args[0]
        if not self._confirm:
            print("确认管理器未初始化")
            return
        ok, msg = await self._confirm.reject(token)
        print(f"{'✓' if ok else '✗'} {msg}")

    async def _cmd_send(self, *args) -> None:
        """发群消息: send <group_id> <text...>"""
        if len(args) < 2:
            print("用法: send <group_id> <消息内容>")
            return
        try:
            group_id = int(args[0])
        except ValueError:
            print("group_id 必须是数字")
            return
        text = " ".join(args[1:])
        if not self._client:
            print("客户端未连接")
            return
        resp = await self._client.send_group_msg(
            group_id=group_id,
            message=[text_segment(text)],
        )
        print(f"发送结果: {'成功' if resp.ok else '失败'} ({resp.retcode})")

    async def _cmd_ban(self, *args) -> None:
        """禁言: ban <group_id> <user_id> [duration]"""
        if len(args) < 2:
            print("用法: ban <group_id> <user_id> [duration秒]")
            return
        try:
            group_id = int(args[0])
            user_id = int(args[1])
        except ValueError:
            print("参数必须是数字")
            return
        duration = int(args[2]) if len(args) > 2 else 600

        if not self._client:
            print("客户端未连接")
            return

        # 提交确认
        if self._confirm:
            token = await self._confirm.submit(
                action_type="set_group_ban",
                params={"group_id": group_id, "user_id": user_id, "duration": duration},
                description=f"禁言 {user_id} 在群 {group_id}（{duration}秒）",
            )
            print(f"已提交确认请求，令牌: {token}")
            print(f"使用 'approve {token}' 批准")
        else:
            resp = await self._client.set_group_ban(group_id, user_id, duration)
            print(f"禁言结果: {'成功' if resp.ok else '失败'}")

    async def _cmd_kick(self, *args) -> None:
        """踢人: kick <group_id> <user_id>"""
        if len(args) < 2:
            print("用法: kick <group_id> <user_id>")
            return
        try:
            group_id = int(args[0])
            user_id = int(args[1])
        except ValueError:
            print("参数必须是数字")
            return

        if self._confirm:
            token = await self._confirm.submit(
                action_type="set_group_kick",
                params={"group_id": group_id, "user_id": user_id},
                description=f"踢出 {user_id} 从群 {group_id}",
            )
            print(f"已提交确认请求，令牌: {token}")
        else:
            resp = await self._client.set_group_kick(group_id, user_id)
            print(f"踢人结果: {'成功' if resp.ok else '失败'}")

    async def _cmd_leave(self, *args) -> None:
        """退群（需确认）: leave <group_id>"""
        if not args:
            print("用法: leave <group_id>")
            return
        try:
            group_id = int(args[0])
        except ValueError:
            print("group_id 必须是数字")
            return

        # 退群必须走确认流程
        if not self._confirm:
            print("确认管理器未初始化，无法退群")
            return

        token = await self._confirm.submit(
            action_type="set_group_leave",
            params={"group_id": group_id},
            description=f"退出群聊 {group_id}",
        )
        print(f"⚠ 退群操作已提交确认，令牌: {token}")
        print(f"  使用 'approve {token}' 确认退群")
        print(f"  使用 'reject {token}' 取消")

    async def _cmd_wl_add(self, *args) -> None:
        """加白名单: wl-add <group_id>"""
        if not args:
            print("用法: wl-add <group_id>")
            return
        try:
            gid = int(args[0])
        except ValueError:
            print("group_id 必须是数字")
            return
        if self._whitelist:
            added = self._whitelist.add_group(gid)
            print(f"{'✓' if added else '·'} 群 {gid} {'已加入' if added else '已在'}白名单")

    async def _cmd_wl_rm(self, *args) -> None:
        """删白名单: wl-rm <group_id>"""
        if not args:
            print("用法: wl-rm <group_id>")
            return
        try:
            gid = int(args[0])
        except ValueError:
            print("group_id 必须是数字")
            return
        if self._whitelist:
            removed = self._whitelist.remove_group(gid)
            print(f"{'✓' if removed else '·'} 群 {gid} {'已移除' if removed else '不在'}白名单")

    async def _cmd_wl_list(self, *args) -> None:
        """列白名单。"""
        if not self._whitelist:
            print("白名单未初始化")
            return
        groups = self._whitelist.list_groups()
        friends = self._whitelist.list_friends()
        print(f"\n群白名单 ({len(groups)}):")
        for gid in groups:
            info = self._whitelist.get_group_info(gid)
            name = info.get("group_name", "?") if info else "?"
            print(f"  {gid} ({name})")
        print(f"\n好友白名单 ({len(friends)}):")
        for fid in friends:
            print(f"  {fid}")

    async def _cmd_backup(self, *args) -> None:
        """手动备份。"""
        backup_mixin = getattr(self._handler, "backup_mixin", None)
        if backup_mixin:
            path = await backup_mixin.backup_all(reason="manual_console")
            if path:
                print(f"✓ 备份完成: {path}")
            else:
                print("✗ 备份失败")
        else:
            print("BackupMixin 未加载")

    async def _cmd_ext_list(self, *args) -> None:
        """列出已加载插件。"""
        exts = getattr(self._handler, "extensions", {})
        if not exts:
            print("当前没有已加载的插件")
            return
        print(f"\n已加载插件 ({len(exts)}):")
        print("-" * 60)
        for name, ext in exts.items():
            status = "✓" if getattr(ext, "enabled", True) else "✗"
            desc = getattr(ext, "description", "")
            priority = getattr(ext, "priority", 100)
            print(f"  {status} {name:<20} 优先级={priority:<3} {desc}")

    async def _cmd_ext_reload(self, *args) -> None:
        """重载插件: ext-reload <name>"""
        if not args:
            print("用法: ext-reload <插件名>")
            return
        name = args[0]
        ext_mgr = getattr(self._handler, "extension_manager", None)
        if not ext_mgr:
            print("插件管理器未初始化")
            return
        # 热重载 = 先卸载再加载
        loaded = await ext_mgr.hot_reload(name)
        if loaded:
            print(f"✓ 插件 {name} 已重载")
        else:
            print(f"✗ 插件 {name} 重载失败")

    async def _cmd_ext_hot(self, *args) -> None:
        """热加载/卸载: ext-hot <load|unload> <name>"""
        if len(args) < 2:
            print("用法: ext-hot <load|unload> <插件名>")
            return
        action, name = args[0].lower(), args[1]
        ext_mgr = getattr(self._handler, "extension_manager", None)
        if not ext_mgr:
            print("插件管理器未初始化")
            return
        if action == "load":
            ok = await ext_mgr.hot_load(name)
            print(f"{'✓' if ok else '✗'} 热加载 {name}")
        elif action == "unload":
            ok = await ext_mgr.hot_unload(name)
            print(f"{'✓' if ok else '✗'} 热卸载 {name}")
        else:
            print("action 必须是 load 或 unload")

    async def _cmd_quit(self, *args) -> None:
        """退出程序。"""
        print("正在关闭...")
        self._running = False
        handler = self._handler
        if handler:
            # 触发关闭流程
            await handler.shutdown()

    # ─── 退群确认辅助 ────────────────────────────────────

    async def confirm_leave_group(self, group_id: int, reason: str = "") -> Tuple[bool, str]:
        """
        发起退群确认流程。
        返回 (是否批准, 消息)。
        如果确认管理器不可用，直接拒绝。
        """
        if not self._confirm:
            return False, "确认管理器未初始化"

        token = await self._confirm.submit(
            action_type="set_group_leave",
            params={"group_id": group_id, "reason": reason},
            description=f"退出群聊 {group_id}（{reason}）",
        )
        return False, f"已提交退群确认，令牌: {token}，等待管理员审批"

    # ─── 关闭 ─────────────────────────────────────────────

    async def mixin_teardown(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[ConsoleMixin] 控制台已关闭")
