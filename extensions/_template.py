"""
Extension 模板 —— 复制此文件并重命名即可开始开发
==================================================
使用方式：
  1. 复制本文件到 extensions/ 目录，改名为 my_ext.py
  2. 修改类名为 MyExt
  3. 按需重写 on_group_message / on_private_message 等方法
  4. 启动服务器后自动冷加载，也可 CLI: load my_ext

权限说明：
  - Extension 只能继承 onebot_server.mixin 中的 Mixin
  - Extension 不能直接访问 WebSocket / Handler / Client
  - Extension 只能通过 self.safe_send_*() 间接发送消息
  - 敏感操作（禁言/踢人/退群）必须走 self.submit_confirm()

继承规则：
  - 继承链：BaseExtension → 你选的 Mixin → 你的 Extension
  - 可选 Mixin：LogMixin / StatsMixin / BackupMixin / ConsoleMixin / TaskMixin
  - Mixin 提供的 safe_send_* / submit_confirm / get_stats 等方法自动可用
"""

# ┌─────────────────────────────────────────────────────────────────────┐
# │ 标准库导入                                                              │
# └─────────────────────────────────────────────────────────────────────┘
import json
from pathlib import Path
from typing import Optional

from onebot_server.events import (
    GroupMessageEvent,
    MetaEvent,
    NoticeEvent,
    PrivateMessageEvent,
    RequestEvent,
)

# ┌─────────────────────────────────────────────────────────────────────┐
# │ 项目内导入 —— 只能从以下模块导入                                       │
# │   • extension_base  : BaseExtension 基类                             │
# │   • mixin           : 可继承的 Mixin 模块                            │
# │   • events          : 事件数据类（只读）                              │
# │   • actions / segments : 构造发送内容                                │
# │   • client          : OneBotClient 类型标注（不直接用）               │
# └─────────────────────────────────────────────────────────────────────┘
from onebot_server.extension_base import BaseExtension
from onebot_server.mixin import LogMixin  # 提供 safe_send_* / 日志记录
from onebot_server.mixin import StatsMixin  # 提供 get_stats / 消息计数
from onebot_server.segments import (
    AtSegment,
    FaceSegment,
    ImageSegment,
    ReplySegment,
    TextSegment,
    build_message,
)
# 下面这个导入仅用于本模板 "示例2: /whoami" 的示范代码
from onebot_server.actions import GetLoginInfoAction  # noqa: F401  (模板示范用)


# ┌─────────────────────────────────────────────────────────────────────┐
# │ Extension 类定义                                                      │
# │                                                                      │
# │ 继承顺序：BaseExtension 必须第一个，Mixin 放后面                        │
# │ priority 越高越先执行（默认 100）                                      │
# └─────────────────────────────────────────────────────────────────────┘
class TemplateExt(BaseExtension, LogMixin, StatsMixin):
    """
    模板插件 —— 展示所有常用写法和最佳实践。

    类名必须全局唯一（不能和别的 Extension 重名）。
    priority 决定同事件多个 Extension 的执行顺序，越大越靠前。
    """

    # ---- 插件元信息（自动读取） ----
    name: str = "template"  # 插件名（CLI 用 load/unload template）
    description: str = "模板插件，展示所有常用 API 写法"
    version: str = "1.0.0"
    author: str = "your_name"
    priority: int = 100  # 执行优先级，越大越先执行

    # ---- 可选：插件私有配置文件路径 ----
    # 放在 extensions/ 目录下，JSON 自动加载/保存
    config_path: Optional[Path] = None

    # ┌───────────────────────────────────────────────────────────────┐
    # │ 生命周期钩子                                                     │
    # └───────────────────────────────────────────────────────────────┘

    async def on_load(self) -> None:
        """
        插件被加载时调用（冷加载 / 热加载都会触发）。
        适合做：读取配置、初始化连接、注册定时任务。
        """
        self.logger.info(f"[{self.name}] 插件加载中...")

        # 示例：加载私有配置
        self.config_path = Path(__file__).parent / f"{self.name}.json"
        self.config = self._load_config()

        # 示例：如果用 TaskMixin，可以注册定时任务
        # await self.schedule_task("heartbeat", 60, self._heartbeat)

        self.logger.info(f"[{self.name}] 插件加载完成 v{self.version}")

    async def on_unload(self) -> None:
        """
        插件被卸载时调用（热卸载 / 冷卸载都会触发）。
        适合做：保存状态、关闭连接、取消定时任务。
        """
        self.logger.info(f"[{self.name}] 插件卸载中...")

        # 示例：保存配置
        self._save_config()

        self.logger.info(f"[{self.name}] 插件已卸载")

    # ┌───────────────────────────────────────────────────────────────┐
    # │ 消息事件处理                                                     │
    # └───────────────────────────────────────────────────────────────┘

    async def on_group_message(
        self,
        event: GroupMessageEvent,
        client,  # OneBotClient，类型标注用字符串避免循环导入
    ) -> None:
        """
        群消息回调。
        所有群消息都会经过这里（前提：没被更高优先级的插件拦截）。

        参数：
            event  : GroupMessageEvent 实例，包含所有消息字段
            client : OneBotClient，可通过 self.safe_send_* 间接使用
        """
        # 获取消息纯文本（自动拼接所有 text 段）
        text = event.get_text().strip()

        # 获取发送者信息
        user_id = event.user_id
        group_id = event.group_id
        nickname = event.sender.nickname

        # ---- 示例 1：简单关键词回复 ----
        if text == "/ping":
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(
                    ReplySegment(event.message_id),  # 回复引用
                    AtSegment.someone(user_id),  # @发送者
                    " pong! 🏓",
                ),
            )
            return

        # ---- 示例 2：调用需要等待结果的 API ----
        if text == "/whoami":
            # call_action 会等待 LLOneBot 回包
            result = await self.call_action(
                GetLoginInfoAction(),
            )
            bot_name = result.get("data", {}).get("nickname", "未知")
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(f"我是 {bot_name}"),
            )
            return

        # ---- 示例 3：敏感操作 → 必须走审批 ----
        if text.startswith("/ban"):
            # 解析参数：/ban 120 → 禁言 120 秒
            parts = text.split()
            duration = int(parts[1]) if len(parts) > 1 else 60

            # 提交审批（非管理员直接拒绝）
            await self.submit_confirm(
                client=client,
                action_name="set_group_ban",
                params={
                    "group_id": group_id,
                    "user_id": user_id,
                    "duration": duration,
                },
                group_id=group_id,
                description=f"禁言 {nickname}({user_id}) {duration}秒",
                # 可选：指定审批群，不填则默认第一个 admin 群
            )
            return

        # ---- 示例 4：发送图片 ----
        if text == "/pic":
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(
                    ImageSegment.url("https://picsum.photos/400/300"),
                ),
            )
            return

        # ---- 示例 5：发送 QQ 表情 ----
        if text == "/face":
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(
                    TextSegment("来个表情："),
                    FaceSegment(face_id=178),  # 178 = 滑稽
                ),
            )
            return

        # ---- 示例 6：调用 StatsMixin 的方法 ----
        if text == "/stats":
            stats = self.get_stats()  # 来自 StatsMixin
            msg = (
                f"📊 统计\n"
                f"  群消息: {stats['group_msg_count']}\n"
                f"  私聊: {stats['private_msg_count']}\n"
                f"  启动时间: {stats['uptime']:.0f}s"
            )
            await self.safe_send_group_msg(
                group_id=group_id,
                message=build_message(msg),
            )
            return

    async def on_private_message(
        self,
        event: PrivateMessageEvent,
        client,
    ) -> None:
        """私聊消息回调。"""
        text = event.get_text().strip()
        user_id = event.user_id

        if text == "/help":
            help_text = (
                "📖 可用命令：\n"
                "  /ping     - 测试连通性\n"
                "  /whoami   - 查询机器人信息\n"
                "  /ban [秒] - 禁言自己（需审批）\n"
                "  /pic      - 发一张图\n"
                "  /face     - 发一个表情\n"
                "  /stats    - 查看统计"
            )
            await self.safe_send_private_msg(
                user_id=user_id,
                message=build_message(help_text),
            )

    # ┌───────────────────────────────────────────────────────────────┐
    # │ 通知 / 请求 / 元事件（可选重写）                                  │
    # └───────────────────────────────────────────────────────────────┘

    async def on_notice(self, event: NoticeEvent, client) -> None:
        """群通知回调（入群/退群/撤回/禁言等）。"""
        # 示例：有人入群时发欢迎
        if event.notice_type == "group_increase":
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=build_message(
                    AtSegment.someone(event.user_id),
                    " 欢迎新成员！🎉",
                ),
            )

    async def on_request(self, event: RequestEvent, client) -> None:
        """加好友 / 加群请求回调。"""
        # 默认不处理，可在此自动同意或拒绝
        pass

    async def on_meta(self, event: MetaEvent, client) -> None:
        """心跳 / 生命周期事件。"""
        # 示例：连接建立时打招呼
        if event.meta_event_type == "lifecycle":
            self.logger.info(f"[{self.name}] WebSocket 连接已建立")

    # ┌───────────────────────────────────────────────────────────────┐
    # │ 工具方法（插件私有）                                             │
    # └───────────────────────────────────────────────────────────────┘

    def _load_config(self) -> dict:
        """加载插件私有配置（不存在则返回默认值）。"""
        defaults = {
            "enabled": True,
            "keywords": ["你好", "在吗"],
            "reply": "我在呢！",
        }
        if self.config_path and self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception as e:
                self.logger.warning(f"[{self.name}] 配置解析失败: {e}")
        return defaults

    def _save_config(self) -> None:
        """保存插件私有配置。"""
        if self.config_path:
            try:
                self.config_path.write_text(
                    json.dumps(self.config, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                self.logger.error(f"[{self.name}] 配置保存失败: {e}")

    async def _heartbeat(self) -> None:
        """定时任务示例（需 TaskMixin）。"""
        self.logger.debug(f"[{self.name}] 心跳 ok")


# ┌─────────────────────────────────────────────────────────────────────┐
# │ 文件末尾必须导出类（管理器通过 inspect 查找子类）                      │
# └─────────────────────────────────────────────────────────────────────┘
# 管理器会扫描 extensions/ 目录下所有 .py 文件，
# 自动发现 BaseExtension 的子类并实例化。
# 只要上面 class 定义存在，无需额外注册代码。
