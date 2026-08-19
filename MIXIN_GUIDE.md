# Mixin 开发完全指南

> 本文档面向插件开发者，详细讲解每个内置 Mixin 的功能、生命周期钩子、可用属性和方法，以及如何在自定义插件（Extension）中继承和使用它们。

---

## 目录

- [一、Mixin 是什么？](#一mixin-是什么)
- [二、Mixin 与 Extension 的关系](#二mixin-与-extension-的关系)
- [三、BaseMixin 基础类](#三basemixin-基础类)
- [四、LogMixin — 日志 Mixin](#四logmixin--日志-mixin)
- [五、BackupMixin — 备份 Mixin](#五backupmixin--备份-mixin)
- [六、ConsoleMixin — 控制台 Mixin](#六consolemixin--控制台-mixin)
- [七、TaskMixin — 任务调度 Mixin](#七taskmixin--任务调度-mixin)
- [八、StatsMixin — 统计 Mixin](#八statsmixin--统计-mixin)
- [九、如何编写自定义 Mixin](#九如何编写自定义-mixin)
- [十、Mixin 继承链示例](#十mixin-继承链示例)
- [附录：完整生命周期时序图](#附录完整生命周期时序图)

---

## 一、Mixin 是什么？

Mixin 是 OneBot 11 Server 的**内核级插件**。与用户级插件（Extension）不同，Mixin 通过**多重继承**直接组合到 `OneBotHandler` 类中，拥有以下特权：

| 能力 | Mixin | Extension |
|------|-------|-----------|
| 多重继承组合到 Handler | ✅ | ❌ |
| 直接访问 WebSocket Client | ✅ | ❌（需通过 `self.client`） |
| 热加载/热卸载 | ❌（需重启） | ✅ |
| 访问 Handler 所有属性 | ✅ | ✅（通过 `self.handler`） |
| 执行优先级排序 | ✅（`mixin_priority`） | ✅（`priority`） |

**核心规则**：
- Mixin 在 `server.py` 中通过 `create_handler_class([...])` 静态组合，进程启动后不可变
- Extension 在运行时通过 `ExtensionManager` 动态加载/卸载
- **Extension 可以继承 Mixin**，从而获得 Mixin 的全部能力

---

## 二、Mixin 与 Extension 的关系

```
OneBotHandler (动态生成)
├── LogMixin      ← 多重继承（静态）
├── BackupMixin   ← 多重继承（静态）
├── ConsoleMixin  ← 多重继承（静态）
├── TaskMixin     ← 多重继承（静态）
├── StatsMixin    ← 多重继承（静态）
├── AdvancedStatsMixin(StatsMixin)  ← Mixin 继承 Mixin
└── BaseExtension (父类)
    ├── EchoExtension
    ├── ModerationExtension
    └── MyCustomExtension(BaseExtension, TaskMixin)  ← Extension 继承 Mixin
```

**关键理解**：`BaseExtension` 本身也继承自 `BaseMixin`。这意味着 Extension 天然就是 Mixin 的"远房亲戚"，可以在 Extension 中通过多继承叠加任意 Mixin 的能力。

---

## 三、BaseMixin 基础类

所有 Mixin 的终极祖先。定义了 Mixin 的基本协议。

### 3.1 类属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `mixin_name` | `str` | Mixin 的唯一标识名 |
| `mixin_priority` | `int` | 执行优先级，**数字越小越先执行** |
| `mixin_enabled` | `bool` | 是否启用（可在子类中覆盖为 `False` 禁用） |

### 3.2 生命周期钩子

| 钩子方法 | 调用时机 | 典型用途 |
|----------|---------|---------|
| `mixin_setup(handler)` | Handler 初始化完成后 | 创建目录、建立连接、启动后台任务 |
| `mixin_on_connect(client)` | WebSocket 连接建立后 | 获取 self_id、初始化状态 |
| `mixin_on_disconnect(client)` | WebSocket 断开后 | 清理连接相关资源 |
| `mixin_on_event(event)` | **每个事件**到达时（最先触发） | 全局日志、全局过滤 |
| `mixin_on_message(event)` | 消息事件（群+私聊） | 消息统计、敏感词过滤 |
| `mixin_on_notice(event)` | 通知事件 | 退群检测、禁言监控 |
| `mixin_on_request(event)` | 请求事件 | 自动审批加群/加好友 |
| `mixin_on_meta(event)` | 元事件（心跳/生命周期） | 健康检查、状态上报 |
| `mixin_on_response(response)` | Action 回包到达时 | 结果日志、失败重试 |
| `mixin_teardown()` | Handler 关闭时（逆序调用） | 关闭文件、取消任务、保存状态 |

### 3.3 在 Extension 中获取 Handler 引用

```python
# 在 Extension 中
self.handler       # → OneBotHandler 实例
self.client        # → OneBotClient 实例（可能为 None）
self.handler.config  # → Config 对象
self.handler.self_id  # → 当前 QQ 号
self.handler.whitelist  # → WhitelistManager
self.handler.confirm_manager  # → ConfirmManager
self.handler.extensions  # → 所有已加载 Extension 字典
```

---

## 四、LogMixin — 日志 Mixin

### 4.1 概述

| 项目 | 值 |
|------|---|
| `mixin_name` | `"log"` |
| `mixin_priority` | `0`（最高优先级，确保最先记录所有事件） |
| 职责 | 结构化日志记录：事件摘要、Action 结果、连接状态 |

### 4.2 初始化参数

```python
class LogMixin(BaseMixin):
    def __init__(
        self,
        log_events: bool = True,    # 是否记录事件日志
        log_actions: bool = True,   # 是否记录 Action 回包日志
        **kwargs,
    )
```

### 4.3 生命周期行为

| 钩子 | 行为 |
|------|------|
| `mixin_on_connect` | 记录 `WebSocket 已连接 | self_id=xxx` |
| `mixin_on_disconnect` | 记录 `WebSocket 已断开`（WARNING 级别） |
| `mixin_on_event` | 按事件类型分发到 `_log_message` / `_log_notice` / `_log_request` / `_log_meta` |
| `mixin_on_response` | 记录 Action 成功/失败（retcode、echo） |
| `mixin_teardown` | 输出运行统计（时长、事件数、Action 数、错误数） |

### 4.4 消息日志记录格式

```
[消息] type=group group=123456 user=789 text='你好世界'
[消息] type=private user=789 text='ping'
[通知] type=group_increase group=123 user=456
[请求] type=group_add user=456 comment='求拉'
[心跳] interval=30000
[Action] OK echo=a1b2c3d4
[Action] FAILED echo=e5f6g7 retcode=1001 msg=...
```

### 4.5 在自定义 Mixin/Extension 中继承

```python
from onebot_server.extension_base import BaseExtension
from onebot_server.mixin.log_mixin import LogMixin

class MyPlugin(BaseExtension, LogMixin):
    """同时拥有 Extension 的灵活性和 LogMixin 的日志能力。"""

    ext_name: str = "my_plugin"
    description: str = "我的插件"
    priority: int = 10

    async def ext_load(self, handler):
        await super().ext_load(handler)  # 别忘了调父类
        logger.info("[MyPlugin] 加载完成")
        return True

    async def ext_on_message(self, event):
        # LogMixin 已经帮你记录了事件摘要
        # 这里只写业务逻辑
        if "报错" in event.get_message_text():
            logger.error(f"[MyPlugin] 检测到报错消息 from {event.user_id}")
```

> **注意**：`LogMixin` 的 `mixin_priority=0` 意味着它总是在其他 Mixin 之前执行。如果你的插件需要依赖其他 Mixin 的处理结果，把优先级设大一些。

---

## 五、BackupMixin — 备份 Mixin

### 5.1 概述

| 项目 | 值 |
|------|---|
| `mixin_name` | `"backup"` |
| `mixin_priority` | `5` |
| 职责 | 监听退群事件自动备份白名单+群列表，支持手动备份和恢复 |

### 5.2 初始化参数

```python
class BackupMixin(BaseMixin):
    def __init__(
        self,
        backup_dir: str = "backups",          # 备份目录
        retention: int = 50,                  # 保留最近 N 份备份
        auto_backup_on_leave: bool = True,    # 退群时自动备份
        whitelist_manager: Optional[WhitelistManager] = None,  # 可外部注入
        **kwargs,
    )
```

### 5.3 核心方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `backup_all(reason="manual")` | 全量备份（白名单+群列表） | `Optional[str]` 备份路径 |
| `backup_whitelist_only(reason="manual")` | 仅备份白名单 | `Optional[str]` 文件路径 |
| `restore_from(backup_path)` | 从备份目录恢复 | `bool` 是否成功 |
| `list_backups()` | 列出所有备份 | `List[Dict]` 备份信息列表 |

### 5.4 自动触发逻辑

```
群通知事件 (notice_type=group_decrease)
    │
    ├─ user_id == self_id  → 机器人被踢 → 触发备份
    ├─ operator_id == self_id → 机器人主动退群 → 触发备份
    └─ 其他人退群 → 不触发
```

### 5.5 备份文件结构

```
backups/
├── backup_20250115_143022_leave_group_123456/
│   ├── group_whitelist.json    # 群白名单快照
│   ├── friend_whitelist.json  # 好友白名单快照
│   └── group_list.json        # 群列表快照
├── backup_20250120_091500_shutdown/
│   └── ...
└── whitelist_20250110_manual.json  # 仅白名单备份（单文件）
```

### 5.6 在插件中使用

#### 场景 1：在 Extension 中手动触发备份

```python
from onebot_server.extension_base import BaseExtension
from onebot_server.mixin.backup_mixin import BackupMixin

class AdminTools(BaseExtension, BackupMixin):
    """管理员工具：手动备份 + 恢复。"""

    ext_name: str = "admin_tools"
    description: str = "管理员工具（备份/恢复）"
    priority: int = 5

    async def ext_on_group_message(self, event):
        text = event.get_message_text().strip()

        # 管理员发送 /backup 手动备份
        if text == "/backup" and self.is_admin(event.user_id):
            path = await self.backup_all(reason=f"manual_by_{event.user_id}")
            if path:
                await self.safe_send_group_msg(
                    group_id=event.group_id,
                    message=[{"type": "text", "data": {"text": f"✅ 备份完成: {path}"}}],
                )
            return

        # 管理员发送 /restore <备份名> 恢复
        if text.startswith("/restore") and self.is_admin(event.user_id):
            parts = text.split()
            if len(parts) < 2:
                return
            backup_name = parts[1]
            ok = await self.restore_from(f"backups/{backup_name}")
            msg = f"{'✅' if ok else '❌'} 恢复{'成功' if ok else '失败'}"
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=[{"type": "text", "data": {"text": msg}}],
            )
            return
```

#### 场景 2：获取备份列表

```python
# 在任意 Extension 方法中
backups = self.list_backups()
for b in backups[:5]:
    print(f"  {b['name']} | 原因={b.get('reason','?')} | 群数={b.get('group_count',0)}")
```

#### 场景 3：在自定义 Mixin 中扩展备份逻辑

```python
from onebot_server.mixin.backup_mixin import BackupMixin

class SmartBackupMixin(BackupMixin):
    """智能备份：除了退群，还在每天凌晨自动备份。"""

    mixin_name: str = "smart_backup"
    mixin_priority: int = 5

    async def mixin_setup(self, handler):
        await super().mixin_setup(handler)
        # 注册每日凌晨 3 点自动备份
        # （需要 TaskMixin 配合，见 TaskMixin 章节）
        task_mixin = getattr(handler, "_task_mixin", None)
        if task_mixin:
            task_mixin.schedule_cron(
                name="daily_backup",
                func=self._daily_backup,
                minute="0", hour="3",
            )

    async def _daily_backup(self):
        logger.info("[SmartBackup] 每日自动备份触发")
        await self.backup_all(reason="daily_auto")
```

---

## 六、ConsoleMixin — 控制台 Mixin

### 6.1 概述

| 项目 | 值 |
|------|---|
| `mixin_name` | `"console"` |
| `mixin_priority` | `10` |
| 职责 | 在终端提供交互式命令行，支持审批、发消息、管理插件等 |

### 6.2 初始化参数

```python
class ConsoleMixin(BaseMixin):
    def __init__(
        self,
        prompt: str = "onebot ",                      # 命令行提示符
        confirm_manager: Optional[ConfirmManager] = None,  # 可外部注入
        whitelist: Optional[WhitelistManager] = None,      # 可外部注入
        **kwargs,
    )
```

### 6.3 内置命令一览

| 命令 | 用法 | 说明 |
|------|------|------|
| `help` | `help` | 显示所有可用命令 |
| `status` | `status` | 查看运行状态（连接、QQ号、待审批数、白名单数、插件数） |
| `pending` | `pending` | 查看所有待审批请求 |
| `approve <token>` | `approve a1b2c3d4e5f6g7h8` | 批准请求 |
| `reject <token>` | `reject a1b2c3d4e5f6g7h8` | 拒绝请求 |
| `send <群号> <内容>` | `send 123456 大家好` | 发送群消息 |
| `ban <群号> <QQ> [时长]` | `ban 123 456 300` | 禁言（提交审批） |
| `kick <群号> <QQ>` | `kick 123 456` | 踢人（提交审批） |
| `leave <群号>` | `leave 123456` | 退群（提交审批） |
| `wl-add <群号>` | `wl-add 123456` | 加白名单 |
| `wl-rm <群号>` | `wl-rm 123456` | 删白名单 |
| `wl-list` | `wl-list` | 列出白名单 |
| `backup` | `backup` | 手动备份 |
| `ext-list` | `ext-list` | 列出已加载插件 |
| `ext-reload <名称>` | `ext-reload echo` | 重载插件 |
| `ext-hot <load|unload> <名称>` | `ext-hot load my_plugin` | 热加载/卸载 |
| `quit` | `quit` | 退出程序 |

### 6.4 扩展自定义命令

ConsoleMixin 提供了 `register_command()` 接口，让你可以在自定义 Mixin 或 Extension 中注册新命令。

```python
from onebot_server.extension_base import BaseExtension
from onebot_server.mixin.console_mixin import ConsoleMixin

class MyAdminExt(BaseExtension, ConsoleMixin):
    """注册自定义控制台命令。"""

    ext_name: str = "my_admin"
    description: str = "自定义管理命令"
    priority: int = 8

    async def ext_load(self, handler):
        await super().ext_load(handler)
        # 获取 ConsoleMixin 实例（已组合到 handler 中）
        console = handler._mixin_proxies  # 不推荐直接访问
        # 更好的方式：在 handler 上找 console mixin
        for proxy in handler._mixin_proxies:
            if proxy.mixin_name == "console":
                proxy.register_command(
                    "mycmd",
                    self._cmd_mycmd,
                    "我的自定义命令",
                )
                break
        return True

    async def _cmd_mycmd(self, *args):
        """自定义命令实现。"""
        print(f"[MyAdmin] 收到参数: {args}")
        # 可以调用 handler 的各种能力
        handler = self.handler
        if handler and handler.client:
            resp = await handler.client.send_group_msg(
                group_id=123456,
                message=[{"type": "text", "data": {"text": "来自控制台命令！"}}],
            )
            print(f"发送结果: {'成功' if resp.ok else '失败'}")
```

### 6.5 在 Mixin 中使用确认流程

```python
# 在任何 Mixin 中，可以通过 handler.confirm_manager 提交敏感操作
token = await self.handler.confirm_manager.submit(
    action_type="set_group_ban",
    params={"group_id": 123, "user_id": 456, "duration": 600},
    description="禁言 456 在群 123（10分钟）",
    executor=999,  # 操作者的 QQ
)
```

### 6.6 控制台输出示例

```
==================================================
 OneBot 11 Server — 交互式控制台
 输入 'help' 查看命令，'quit' 退出
==================================================
onebot status

========================================
 连接状态: 已连接
 QQ 号: 123456789
 运行时间: 3600s
 待审批: 2 条
 白名单群: 15 个
 已加载插件: 4 个
========================================
onebot pending

令牌              操作            描述                    状态
------------------------------------------------------------
a1b2c3d4e5f6g7h8  set_group_kick  踢出 456 从群 123       等待审批
h8g7f6e5d4c3b2a1  set_group_leave 退出群聊 789           等待审批
onebot approve a1b2c3d4e5f6g7h8
✓ 已批准: set_group_kick
```

---

## 七、TaskMixin — 任务调度 Mixin

### 7.1 概述

| 项目 | 值 |
|------|---|
| `mixin_name` | `"task"` |
| `mixin_priority` | `20` |
| 职责 | 提供定时任务和周期性任务能力（间隔/一次性/cron 三种模式） |

### 7.2 三种任务类型

#### ① 间隔任务（Interval）

按固定间隔重复执行。

```python
def schedule_interval(
    self,
    name: str,           # 任务名（唯一标识）
    func: TaskFunc,      # 异步函数（协程函数）
    interval: float,     # 间隔秒数
    immediate: bool = False,  # 是否立即执行一次
) -> bool
```

#### ② 一次性任务（Once）

延迟指定秒数后执行一次。

```python
def schedule_once(
    self,
    name: str,
    func: TaskFunc,
    delay: float,    # 延迟秒数
) -> bool
```

#### ③ Cron 任务

类 cron 表达式，支持 `*` 和 `*/n` 步长语法。

```python
def schedule_cron(
    self,
    name: str,
    func: TaskFunc,
    minute: str = "*",    # 分钟 (0-59)
    hour: str = "*",      # 小时 (0-23)
    day: str = "*",       # 日期 (1-31)
    month: str = "*",     # 月份 (1-12)
    weekday: str = "*",   # 星期 (0-6, 0=周一)
) -> bool
```

### 7.4 Cron 表达式示例

| 表达式 | 含义 |
|--------|------|
| `"0", "*", "*", "*", "*"` | 每小时整点 |
| `"0", "3", "*", "*", "*"` | 每天凌晨 3:00 |
| `"*/5", "*", "*", "*", "*"` | 每 5 分钟 |
| `"30", "8", "*", "*", "0"` | 每周一 08:30 |
| `"0", "0", "1", "*", "*"` | 每月 1 号零点 |
| `"0", "12", "*", "*", "5"` | 每周五中午 12:00 |

### 7.5 任务管理 API

| 方法 | 说明 |
|------|------|
| `list_tasks()` | 列出所有任务（名称、类型、状态、运行次数、下次运行时间） |
| `cancel_task(name)` | 取消并删除任务 |
| `enable_task(name, enabled=True)` | 启用/禁用任务 |

### 7.6 在 Extension 中使用

```python
from onebot_server.extension_base import BaseExtension
from onebot_server.mixin.task_mixin import TaskMixin

class SchedulerExt(BaseExtension, TaskMixin):
    """定时任务示例插件。"""

    ext_name: str = "scheduler"
    description: str = "定时播报/提醒"
    priority: int = 50

    async def ext_load(self, handler):
        await super().ext_load(handler)

        # ① 每 30 秒报时
        self.schedule_interval(
            name="tick_30s",
            func=self._tick,
            interval=30,
            immediate=False,
        )

        # ② 10 秒后发送一条欢迎消息（一次性）
        self.schedule_once(
            name="welcome_delay",
            func=self._send_welcome,
            delay=10,
        )

        # ③ 每天 8:00 群早安播报
        self.schedule_cron(
            name="good_morning",
            func=self._good_morning,
            minute="0", hour="8",
        )

        # ④ 每 5 分钟检查一次（步长语法）
        self.schedule_cron(
            name="health_check",
            func=self._health_check,
            minute="*/5",
        )

        logger.info("[SchedulerExt] 所有定时任务已注册")
        return True

    async def _tick(self):
        """每 30 秒执行。"""
        logger.debug("[SchedulerExt] tick...")

    async def _send_welcome(self):
        """延迟 10 秒后发送欢迎消息。"""
        client = self.client
        if not client:
            return
        await client.send_group_msg(
            group_id=123456,
            message=[{"type": "text", "data": {"text": "🎉 服务器已就绪！"}}],
        )

    async def _good_morning(self):
        """每天 8:00 早安。"""
        client = self.client
        if not client:
            return
        await client.send_group_msg(
            group_id=123456,
            message=[{"type": "text", "data": {"text": "☀️ 早上好，新的一天开始了！"}}],
        )

    async def _health_check(self):
        """健康检查。"""
        handler = self.handler
        if handler and handler.client:
            logger.debug(f"[SchedulerExt] 连接正常 | uptime={handler.client.uptime:.0f}s")

    async def ext_on_group_message(self, event):
        """运行时管理任务。"""
        text = event.get_message_text().strip()

        if text == "/tasks" and self.is_admin(event.user_id):
            tasks = self.list_tasks()
            lines = ["📋 定时任务列表:"]
            for t in tasks:
                status = "✓" if t["enabled"] else "✗"
                lines.append(f" {status} {t['name']} | {t['type']} | 已运行 {t['run_count']} 次")
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=[{"type": "text", "data": {"text": "\n".join(lines)}}],
            )
            return

        if text.startswith("/cancel") and self.is_admin(event.user_id):
            name = text.split()[1] if len(text.split()) > 1 else ""
            if name:
                ok = self.cancel_task(name)
                msg = f"{'✅' if ok else '❌'} 取消任务 {name}"
                await self.safe_send_group_msg(
                    group_id=event.group_id,
                    message=[{"type": "text", "data": {"text": msg}}],
                )
            return
```

### 7.7 注意事项

- **任务函数必须是 `async def`**（协程函数），不能传普通函数
- 任务异常会被自动捕获并记录日志，**不会**导致调度器停止
- `schedule_once` 执行后自动删除，无需手动清理
- 调度精度为 **1 秒**（`asyncio.sleep(1)`）
- 不要在任务函数中执行**阻塞操作**（如 `time.sleep()`、`requests.get()`），会卡住整个事件循环

---

## 八、StatsMixin — 统计 Mixin

### 8.1 概述

| 项目 | 值 |
|------|---|
| `mixin_name` | `"stats"` |
| `mixin_priority` | `3`（在 LogMixin 之后、业务逻辑之前） |
| 职责 | 统计消息类型、群活跃度、用户活跃度、时段分布 |

### 8.2 初始化参数

```python
class StatsMixin(BaseMixin):
    def __init__(self, top_n: int = 5)  # 排行榜显示前 N 名
```

### 8.3 统计维度

| 维度 | 存储 | 说明 |
|------|------|------|
| 总消息数 | `_total_messages: int` | 累计所有消息 |
| 按消息类型 | `_by_type: Counter` | group / private / unknown |
| 按群 | `_by_group: Counter` | 每个群的消息数 |
| 按用户 | `_by_user: Counter` | 每个用户的消息数 |
| 按小时 | `_by_hour: Counter` | 24 小时分布 |

### 8.4 查询接口

```python
def get_report() -> Dict[str, Any]
```
返回结构化报告字典：
```python
{
    "uptime_seconds": 3600.0,
    "total_messages": 1523,
    "messages_per_minute": 25.4,
    "by_type": {"group": 1400, "private": 123},
    "top_groups": [(123456, 800), (789012, 600)],
    "top_users": [(111, 200), (222, 150)],
    "by_hour": {9: 50, 10: 120, 11: 80, ...},
}
```

```python
def print_report() -> str
```
返回人类可读的文本报告（带 emoji）。

### 8.5 生命周期行为

| 钩子 | 行为 |
|------|------|
| `mixin_on_message(event)` | 累加各类计数器 |
| `mixin_teardown()` | 输出完整统计报告到日志 |

### 8.6 在插件中使用

```python
from onebot_server.extension_base import BaseExtension
from onebot_server.mixin.stats_mixin import StatsMixin

class StatsBot(BaseExtension, StatsMixin):
    """统计机器人：回复消息排行榜。"""

    ext_name: str = "stats_bot"
    description: str = "群消息统计"
    priority: int = 60

    async def ext_load(self, handler):
        await super().ext_load(handler)
        # 设置 TOP 10
        self._by_group = None  # 不限制
        return True

    async def ext_on_group_message(self, event):
        text = event.get_message_text().strip()

        if text == "/stats":
            report = self.print_report()
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=[{"type": "text", "data": {"text": report}}],
            )
            return

        if text == "/rank":
            # 只发送当前群的排行
            gid = event.group_id
            count = self._by_group.get(gid, 0)
            lines = [f"📊 本群统计:", f"  总消息数: {count}"]
            await self.safe_send_group_msg(
                group_id=event.group_id,
                message=[{"type": "text", "data": {"text": "\n".join(lines)}}],
            )
            return
```

### 8.7 继承扩展：AdvancedStatsMixin

项目内置了 `AdvancedStatsMixin`，演示了如何**继承一个 Mixin 并叠加新能力**：

```python
class AdvancedStatsMixin(StatsMixin):
    """
    继承 StatsMixin，额外统计：
    - 图片/表情/@ 消息数量
    - 平均消息长度
    - 命令使用频率
    """

    mixin_name: str = "stats_advanced"
    mixin_priority: int = 4  # 比父类稍低，确保父类先统计

    def __init__(self, top_n: int = 5):
        super().__init__(top_n=top_n)
        self._image_count: int = 0
        self._face_count: int = 0
        self._at_count: int = 0
        self._total_text_length: int = 0
        self._command_count: Counter = Counter()

    async def mixin_on_message(self, event):
        # 先调用父类统计
        await super().mixin_on_message(event)

        # 额外统计消息段
        for seg in event.message:
            seg_type = seg.type
            if seg_type == "image":
                self._image_count += 1
            elif seg_type == "face":
                self._face_count += 1
            elif seg_type == "at":
                self._at_count += 1
            elif seg_type == "text":
                text = seg.data.get("text", "")
                if text.startswith("/"):
                    self._command_count[text.split()[0].lower()] += 1

    def print_report(self):
        # 扩展报告
        base = super().print_report()
        avg = self._total_text_length / max(self._total_messages, 1)
        extra = f"\n── 高级统计 ──\n 图片: {self._image_count}\n 表情: {self._face_count}\n @消息: {self._at_count}\n 平均长度: {avg:.1f}字符"
        return base + extra
```

**继承要点**：
1. `super().__init__()` 调用父类构造
2. `await super().mixin_on_message(event)` 调用父类钩子（注意是 `await`）
3. `super().print_report()` 获取父类报告并追加内容
4. `mixin_priority` 设得比父类大，确保父类先执行

---

## 九、如何编写自定义 Mixin

### 9.1 最小模板

```python
# onebot_server/mixin/my_mixin.py
"""
my_mixin.py — 我的自定义 Mixin
"""

from typing import Any
from ..logger import get_logger
from ..mixin_base import BaseMixin

logger = get_logger()

class MyMixin(BaseMixin):
    """我的自定义 Mixin。"""

    mixin_name: str = "my_mixin"
    mixin_priority: int = 15  # 调整执行顺序

    def __init__(self, custom_param: str = "default", **kwargs):
        self.custom_param = custom_param
        # 统计/状态变量
        self._counter: int = 0
        # 必须调用父类
        super().__init__(**kwargs)

    # ─── 生命周期 ─────────────────────────────────

    async def mixin_setup(self, handler: Any) -> None:
        """初始化（handler 已就绪）。"""
        self._handler = handler
        logger.info(f"[MyMixin] 初始化 | param={self.custom_param}")

    async def mixin_on_connect(self, client: Any) -> None:
        """WebSocket 连接建立。"""
        self._client = client
        self.self_id = getattr(client, "self_id", 0)
        logger.info(f"[MyMixin] 已连接 | self_id={self.self_id}")

    async def mixin_on_message(self, event: Any) -> None:
        """每条消息触发。"""
        self._counter += 1

    async def mixin_on_notice(self, event: Any) -> None:
        """通知事件。"""
        pass

    async def mixin_on_response(self, response: Any) -> None:
        """Action 回包。"""
        pass

    async def mixin_teardown(self) -> None:
        """关闭清理。"""
        logger.info(f"[MyMixin] 统计: 处理了 {self._counter} 条消息")
```

### 9.2 注册到 Server

在 `server.py`（或你的启动脚本）中，将自定义 Mixin 加入组合列表：

```python
from onebot_server.handler import create_handler_class
from onebot_server.mixin.log_mixin import LogMixin
from onebot_server.mixin.backup_mixin import BackupMixin
from onebot_server.mixin.console_mixin import ConsoleMixin
from onebot_server.mixin.task_mixin import TaskMixin
from onebot_server.mixin.stats_mixin import StatsMixin
from onebot_server.mixin.my_mixin import MyMixin  # ← 你的自定义 Mixin

# 组合所有 Mixin
mixin_classes = [
    LogMixin,
    BackupMixin,
    ConsoleMixin,
    TaskMixin,
    StatsMixin,
    MyMixin,  # ← 加入列表
]

HandlerClass = create_handler_class(mixin_classes)
handler = HandlerClass(config=config)
```

### 9.3 Mixin 之间的依赖与协作

```python
class SmartMixin(BaseMixin):
    """依赖其他 Mixin 的能力。"""

    mixin_name: str = "smart"
    mixin_priority: int = 25

    async def mixin_setup(self, handler):
        self._handler = handler
        # 获取其他 Mixin 的代理对象
        for proxy in handler._mixin_proxies:
            if proxy.mixin_name == "task":
                # 注册定时任务
                proxy.schedule_interval(
                    name="smart_check",
                    func=self._periodic_check,
                    interval=60,
                )
            elif proxy.mixin_name == "stats":
                self._stats = proxy  # 保存引用供后续使用

    async def _periodic_check(self):
        # 使用 StatsMixin 的数据
        if hasattr(self, "_stats"):
            report = self._stats.get_report()
            logger.info(f"[SmartMixin] 当前消息速率: {report['messages_per_minute']:.1f}/min")
```

### 9.4 在 Extension 中多继承多个 Mixin

```python
class SuperBot(BaseExtension, TaskMixin, BackupMixin, StatsMixin):
    """
    一个 Extension 同时拥有：
    - TaskMixin：定时任务
    - BackupMixin：备份恢复
    - StatsMixin：消息统计
    """

    ext_name: str = "super_bot"
    description: str = "全能机器人"
    priority: int = 10

    async def ext_load(self, handler):
        await super().ext_load(handler)
        # 现在 self 拥有了三个 Mixin 的全部方法
        self.schedule_interval("heartbeat", self._heartbeat, 300)
        return True

    async def _heartbeat(self):
        # 使用 StatsMixin 的数据
        report = self.get_report()
        logger.info(f"[SuperBot] 心跳 | {report['total_messages']} 条消息")
        # 使用 BackupMixin 的能力
        if report['total_messages'] > 10000:
            await self.backup_all(reason="auto_10k_messages")
```

---

## 十、Mixin 继承链示例

### 10.1 完整项目实际组合

```
BaseMixin (mixin_base.py)
├── LogMixin (priority=0)
│   └── 监听所有事件 → 结构化日志
│
├── BackupMixin (priority=5)
│   └── 监听 group_decrease → 自动备份
│
├── StatsMixin (priority=3)
│   └── 监听消息 → 统计计数
│   └── AdvancedStatsMixin(StatsMixin) (priority=4)
│       └── 扩展统计：图片/表情/命令
│
├── ConsoleMixin (priority=10)
│   └── 交互式命令行 + 审批管理
│
└── TaskMixin (priority=20)
    └── 定时任务调度器

最终 MRO（方法解析顺序）：
DynamicOneBotHandler → LogMixin → StatsMixin → AdvancedStatsMixin
→ BackupMixin → ConsoleMixin → TaskMixin → BaseMixin → object
```

### 10.2 自定义 Mixin 继承图

```
BaseMixin
├── LogMixin
├── BackupMixin
├── ConsoleMixin
├── TaskMixin
├── StatsMixin
│   └── AdvancedStatsMixin
└── MyCustomMixin
    └── MyBetterMixin(MyCustomMixin, TaskMixin)
        └── UltraBot(BaseExtension, MyBetterMixin, StatsMixin)
```

---

## 附录：完整生命周期时序图

```
                    ┌─────────────────────────────────────────┐
                    │           程序启动 (main.py)              │
                    └────────────────┬────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │  create_handler_class([Mixin列表])       │
                    │  → 动态生成 Handler 类                   │
                    └────────────────┬────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │  Handler.__init__(config, whitelist,     │
                    │                      confirm_manager)    │
                    └────────────────┬────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │  WebSocket Server 启动                  │
                    │  等待 LLOneBot 连接...                   │
                    └────────────────┬────────────────────────┘
                                     │
                            ╔═══════▼═══════╗
                            ║  WS 连接建立   ║
                            ╚═══════╤═══════╝
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │  handler.attach_client(client)           │
                    │  ① _collect_mixins() → 按 priority 排序  │
                    │  ② _setup_mixins()                      │
                    │     → LogMixin.mixin_setup    (priority 0)│
                    │     → StatsMixin.mixin_setup   (priority 3)│
                    │     → BackupMixin.mixin_setup  (priority 5)│
                    │     → ConsoleMixin.mixin_setup (priority 10)│
                    │     → TaskMixin.mixin_setup    (priority 20)│
                    │  ③ Extension.ext_on_connect()            │
                    └────────────────┬────────────────────────┘
                                     │
                            ╔═══════▼═══════╗
                            ║  事件循环开始   ║
                            ╚═══════╤═══════╝
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
    │  消息事件      │    │  通知事件      │    │  请求事件      │
    │ group/private │    │ ban/kick/...  │    │ add_friend... │
    └───────┬───────┘    └───────┬───────┘    └───────┬───────┘
            │                    │                    │
            ▼                    ▼                    ▼
    ┌──────────────────────────────────────────────────────┐
    │ 按 priority 依次调用每个 Mixin 的对应钩子              │
    │ + 每个 Extension 的对应钩子                            │
    └──────────────────────────────────────────────────────┘
                                     │
                            ╔═══════▼═══════╗
                            ║  WS 断开       ║
                            ╚═══════╤═══════╝
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │  handler.detach_client(client)          │
                    │  → 逆序调用 mixin_on_disconnect        │
                    └────────────────┬────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │  handler.shutdown()                     │
                    │  ① Extension.ext_unload()               │
                    │  ② 逆序调用 mixin_teardown()            │
                    │     → TaskMixin (20) → Console (10)     │
                    │     → Backup (5) → Stats (3) → Log (0)  │
                    │  ③ client.close()                       │
                    └─────────────────────────────────────────┘
```

---

## 快速参考卡

### Mixin 优先级速查

| 优先级 | Mixin | 核心职责 |
|--------|-------|---------|
| **0** | LogMixin | 日志记录（最先执行） |
| **3** | StatsMixin | 消息统计 |
| **4** | AdvancedStatsMixin | 高级统计（继承 StatsMixin） |
| **5** | BackupMixin | 退群备份 |
| **10** | ConsoleMixin | 交互式控制台 |
| **20** | TaskMixin | 定时任务调度 |

### Extension 常用模式速查

```python
# 模式 1：最小 Extension（只用 BaseExtension）
class SimpleExt(BaseExtension):
    ext_name = "simple"
    async def ext_on_message(self, event): ...

# 模式 2：Extension + 1 个 Mixin
class TimerExt(BaseExtension, TaskMixin):
    async def ext_load(self, handler):
        await super().ext_load(handler)
        self.schedule_interval("tick", self._tick, 60)

# 模式 3：Extension + 多个 Mixin
class PowerExt(BaseExtension, TaskMixin, BackupMixin, StatsMixin):
    async def ext_load(self, handler):
        await super().ext_load(handler)
        self.schedule_interval("backup", lambda: self.backup_all("auto"), 3600)

# 模式 4：Mixin 继承 Mixin（自定义高级 Mixin）
class SuperStats(StatsMixin):
    mixin_name = "super_stats"
    mixin_priority = 3
    async def mixin_on_message(self, event):
        await super().mixin_on_message(event)  # 先调父类
        # 再加自定义逻辑
```

---

> 📖 **更多文档**：
> - `EXTENSION_QUICKSTART.md` — 5 分钟写第一个插件
> - `DOCUMENTATION.md` — 完整技术文档（1700+ 行）
> - `ARCHITECTURE.md` — 架构图（5 张 Mermaid 图）
