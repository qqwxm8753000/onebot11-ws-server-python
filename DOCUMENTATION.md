# OneBot 11 Server 完整技术文档

> 版本：2.0.0 | 语言：Python 3.9+ | 协议：OneBot 11（反向 WebSocket）
> 适用场景：自写 QQ 机器人后端，对接 LLOneBot，不依赖 NoneBot/Koishi 等框架。

---

## 目录

- [第一章 项目概述](#第一章-项目概述)
- [第二章 架构设计](#第二章-架构设计)
- [第三章 快速开始](#第三章-快速开始)
- [第四章 配置文件详解](#第四章-配置文件详解)
- [第五章 核心模块](#第五章-核心模块)
- [第六章 Mixin 系统](#第六章-mixin-系统)
- [第七章 Extension 系统](#第七章-extension-系统)
- [第八章 事件模型](#第八章-事件模型)
- [第九章 Action API 大全](#第九章-action-api-大全)
- [第十章 消息段构造](#第十章-消息段构造)
- [第十一章 敏感操作确认机制](#第十一章-敏感操作确认机制)
- [第十二章 白名单与备份](#第十二章-白名单与备份)
- [第十三章 CLI 命令行](#第十三章-cli-命令行)
- [第十四章 日志系统](#第十四章-日志系统)
- [第十五章 自定义 Mixin 教程](#第十五章-自定义-mixin-教程)
- [第十六章 自定义 Extension 教程](#第十六章-自定义-extension-教程)
- [第十七章 LLOneBot 对接指南](#第十七章-llonebot-对接指南)
- [第十八章 测试](#第十八章-测试)
- [第十九章 故障排查](#第十九章-故障排查)
- [第二十章 API 速查表](#第二十章-api-速查表)
- [附录 文件清单](#附录-文件清单)

---

## 第一章 项目概述

### 1.1 这是什么

OneBot 11 Server 是一个**自写的 QQ 机器人后端**，通过反向 WebSocket 与 LLOneBot 对接，让你在不依赖任何第三方框架（NoneBot/Koishi/OlivOS）的情况下，用纯 Python 实现 QQ 机器人全部功能。

### 1.2 核心特性

| 特性 | 说明 |
|------|------|
| 🔌 反向 WebSocket | LLOneBot 主动连你，无需公网 IP |
| 🧩 Mixin 组合 | 用多重继承把功能模块组合到 Handler，优先级可控 |
| 🔥 Extension 热加载 | 插件目录放文件即生效，支持热卸载/热重载/冷加载/冷卸载 |
| 🔒 敏感操作确认 | 退群/踢人/禁言需管理员审批，防止误操作 |
| 💾 自动备份 | 退群时自动备份白名单和群列表到 JSON |
| 📝 TOML 配置 | 所有参数集中管理，支持热重载 |
| 📊 Loguru 日志 | 控制台彩色 + 文件按大小轮转 |
| 🖥️ CLI 命令行 | 运行时查看状态、审批请求、重载插件 |
| 🔗 Mixin 继承 Mixin | 高级 Mixin 可继承基础 Mixin 扩展能力 |

### 1.3 与 NoneBot 的对比

| 维度 | NoneBot2 | 本项目 |
|------|----------|--------|
| 依赖 | 重（FastAPI + 一堆 adapter） | 轻（仅 websockets + loguru） |
| 协议 | 通过 adapter 适配 | 直接原生 OneBot 11 |
| 扩展 | 插件系统 | Extension + Mixin 双层 |
| 学习成本 | 中 | 低（直接处理 JSON 事件） |
| 可控性 | 框架封装深 | 全链路透明 |
| 适合场景 | 复杂插件生态 | 轻量/定制化/学习协议 |

---

## 第二章 架构设计

### 2.1 整体架构图

```
                    ┌─────────────────────────────────┐
                    │          LLOneBot (QQ 端)        │
                    │    作为 WebSocket 客户端连出      │
                    └────────────┬────────────────────┘
                                 │ 反向 WS (ws://ip:port)
                                 ▼
                    ┌─────────────────────────────────┐
                    │       OneBotServer (本程序)       │
                    │  ┌───────────────────────────┐  │
                    │  │   WebSocket Server         │  │
                    │  │   (server.py)             │  │
                    │  └────────┬──────────────────┘  │
                    │           ▼                      │
                    │  ┌───────────────────────────┐  │
                    │  │   OneBotHandler            │  │
                    │  │   (handler.py)             │  │
                    │  │   ← 由 Mixin 动态组合      │  │
                    │  └──┬──────────┬─────────────┘  │
                    │     │          │                 │
                    │     ▼          ▼                 │
                    │  ┌──────┐  ┌──────────┐         │
                    │  │Mixin │  │Extension │         │
                    │  │ 系统 │  │  系统    │         │
                    │  └──────┘  └──────────┘         │
                    │     │          │                 │
                    │     ▼          ▼                 │
                    │  ┌────────────────────────┐      │
                    │  │   OneBotClient          │      │
                    │  │   (client.py)           │      │
                    │  │   发送 Action → LLOneBot│      │
                    │  └────────────────────────┘      │
                    └─────────────────────────────────┘
```

### 2.2 数据流

1. **LLOneBot → 本程序（事件流）**
   - LLOneBot 通过反向 WS 连入
   - 发送 JSON 事件（message/notice/request/meta_event）
   - `OneBotHandler.handle_event()` 接收并分发

2. **本程序 → LLOneBot（动作流）**
   - `OneBotClient.send_action()` 发送 JSON Action
   - LLOneBot 执行后回包（带 echo 配对）
   - `await client.call()` 返回结果

### 2.3 三层继承体系

```
BaseEvent (ABC, dataclass)
├── MessageEvent
│   ├── GroupMessageEvent
│   └── PrivateMessageEvent
├── NoticeEvent
├── RequestEvent
├── MetaEvent
└── UnknownEvent

BaseAction (ABC)
├── SendGroupMsgAction
├── SendPrivateMsgAction
├── SendMsgAction
├── GetLoginInfoAction
├── SetGroupBanAction
├── SetGroupKickAction
├── SetGroupLeaveAction
└── ... (20+ 个)

BaseMixin (ABC)
├── LogMixin
├── BackupMixin
├── ConsoleMixin
├── TaskMixin
└── StatsMixin (继承 StatsMixin 基础类)
```

### 2.4 Extension vs Mixin 的区别

| 维度 | Mixin | Extension |
|------|--------|------------|
| 加载时机 | 启动时组合到 Handler 类 | 运行时动态加载/卸载 |
| 修改方式 | 修改源码后重启 | 放文件即生效 |
| 能否操作 WS | ✅ 可以直接发 Action | ❌ 只能通过 `safe_send_*` |
| 优先级 | MRO 顺序决定 | `priority` 字段决定 |
| 适合场景 | 核心功能（日志/备份/审批） | 业务插件（复读/自动回复） |
| 热重载 | ❌ 需重启 | ✅ 文件变更自动重载 |

---

## 第三章 快速开始

### 3.1 环境要求

- Python 3.9+
- Windows 10+ / Linux / macOS
- LLOneBot 已安装并运行在 NTQQ 上

### 3.2 安装

```bash
# 克隆或解压项目
cd onebot11_server

# 安装依赖（仅两个）
pip install websockets loguru
```

### 3.3 配置

编辑 `config.toml`，**至少修改以下两项**：

```toml
[server]
access_token = "改成你自己的随机长字符串"

[admin]
admin_qq = [你的QQ号]
```

### 3.4 启动

```bash
python main.py
```

看到以下日志即成功：

```
==================================================
  OneBot 11 Server 初始化完成
  监听: 0.0.0.0:8765
  Mixin: 4 个
  插件目录: /.../onebot_server/extensions
==================================================
[Server] 启动 WebSocket 服务 ws://0.0.0.0:8765/
[ExtMgr] 冷加载完成: 4/4 个插件
[Server] WebSocket 服务已就绪，等待 LLOneBot 连接...
```

### 3.5 配置 LLOneBot

在 QQ → 设置 → LLOneBot：
- 启用反向 WebSocket：✅
- 反向 WS 地址：`ws://127.0.0.1:8765/`
- Access Token：和 `config.toml` 里一致

连接成功后日志显示：

```
[Server] 新连接来自 ('127.0.0.1', 54321)
[Handler] LLOneBot 已连接
```

### 3.6 验证

群内 `@机器人 /echo 测试` → 机器人复读即全链路通。

---

## 第四章 配置文件详解

### 4.1 完整配置示例

```toml
# ============================================================
# OneBot 11 Server 主配置文件
# 修改后部分项支持热重载（需重启）
# ============================================================

[server]
host = "0.0.0.0"          # 监听地址，0.0.0.0 接受所有网卡
port = 8765                 # 监听端口
path = "/"                   # WS 路径
access_token = "你的token"   # 鉴权令牌（必改！）
heartbeat_timeout = 60       # 心跳超时（秒）
action_timeout = 10          # Action 调用超时（秒）

[logging]
level = "INFO"               # DEBUG / INFO / WARNING / ERROR
log_dir = "logs"             # 日志目录（自动创建）
console = true               # 是否输出到控制台
max_size = 10                # 单文件最大 MB
retention = 30               # 保留文件数

[admin]
admin_qq = [10001, 10002]   # 管理员 QQ 列表
confirm_timeout = 300        # 确认请求超时（秒）

[backup]
backup_dir = "backups"       # 备份目录
auto_backup_on_leave = true  # 退群时自动备份
backup_retention = 50        # 备份保留数量

[extension]
ext_dir = "extensions"       # 插件目录（相对路径自动指向包内）
hot_reload = true            # 文件变更自动重载
watch_interval = 2           # 检测间隔（秒）
ext_suffix = ".py"           # 插件文件后缀

[mixin]
mixin_dir = "mixin"         # Mixin 目录
auto_load = [                # 启动自动加载的 Mixin（按优先级从低到高）
    "log_mixin",
    "backup_mixin",
    "console_mixin",
    "task_mixin",
]
```

### 4.2 配置项说明

#### server 段

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| host | string | "0.0.0.0" | 监听 IP，公网部署建议绑具体网卡 |
| port | int | 8765 | WS 端口 |
| path | string | "/" | WS 子路径 |
| access_token | string | "" | Bearer Token，留空不鉴权（不安全） |
| heartbeat_timeout | int | 60 | 超过此秒数未收到心跳则断连 |
| action_timeout | int | 10 | `call()` 等待 Action 回包的超时 |

#### logging 段

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| level | string | "INFO" | 日志级别 |
| log_dir | string | "logs" | 日志存放目录 |
| console | bool | true | 是否同时输出到终端 |
| max_size | int | 10 | 单文件 MB，超出自动轮转 |
| retention | int | 30 | 保留多少个日志文件 |

#### admin 段

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| admin_qq | int[] | [] | 拥有审批权限的 QQ 号 |
| confirm_timeout | int | 300 | 确认请求有效期（秒） |

#### backup 段

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| backup_dir | string | "backups" | 备份目录 |
| auto_backup_on_leave | bool | true | 退群时是否自动备份 |
| backup_retention | int | 50 | 保留多少份备份 |

#### extension 段

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| ext_dir | string | "extensions" | 插件目录，相对路径自动解析为包内绝对路径 |
| hot_reload | bool | true | 文件变更自动热重载 |
| watch_interval | int | 2 | 文件监控间隔（秒） |
| ext_suffix | string | ".py" | 插件文件后缀 |

#### mixin 段

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| mixin_dir | string | "mixin" | Mixin 目录 |
| auto_load | string[] | [...] | 启动时自动组合的 Mixin 模块名列表 |

### 4.3 路径解析规则

配置文件中的相对路径（如 `"extensions"`、`"mixin"`）会被自动解析为**包内绝对路径**：

```
config.toml:  ext_dir = "extensions"
实际路径:     /.../onebot11_server/onebot_server/extensions/

config.toml:  mixin_dir = "mixin"
实际路径:     /.../onebot11_server/onebot_server/mixin/
```

这是为了避免项目根目录被各种运行时文件夹污染。

---

## 第五章 核心模块

### 5.1 server.py — WebSocket 服务器

**职责**：监听端口、鉴权、管理连接生命周期、组装 Handler、启动/停止 Extension 监控。

**关键类**：`OneBotServer`

```python
from onebot_server import OneBotServer

server = OneBotServer(
    config_path="config.toml",   # 配置文件路径
    handler_class=None,            # 可选：自定义 Handler 类
    mixin_classes=None,            # 可选：自定义 Mixin 列表
)
server.run_forever()              # 阻塞运行
```

**内部流程**：
1. 加载 TOML 配置
2. 初始化 Loguru
3. 创建 ConfirmManager + WhitelistManager
4. 根据 `mixin.auto_load` 加载 Mixin 类
5. `create_handler_class(mixins)` 动态生成 Handler 类
6. 创建 Handler 实例 + ExtensionManager
7. `await start()` → 冷加载插件 → 启动 WS 服务 → 等待连接

### 5.2 handler.py — 事件枢纽

**职责**：接收事件 → 分发到对应 Mixin/Extension → 收集响应。

**关键机制**：
- `_MixinProxy`：为每个 Mixin 创建代理对象，隔离命名空间
- `create_handler_class(mixins)`：动态多重继承，生成 `DynamicOneBotHandler`
- MRO 顺序 = 执行优先级（**排在前面的先执行**）

```python
# handler.py 核心分发逻辑（简化）
async def handle_event(self, event_dict: dict) -> Optional[dict]:
    # 1. 解析事件类型
    event = BaseEvent.from_dict(event_dict)
    
    # 2. 依次调用每个 Mixin 的 mixin_on_event
    for mixin_info in self._mixins:
        proxy = _MixinProxy(self, mixin_info)
        method = getattr(proxy, "mixin_on_event", None)
        if method:
            result = await method(event)
            if result:  # 短路：第一个返回非 None 的胜出
                return result
    
    # 3. 分发到具体类型
    if event.post_type == "message":
        await self._dispatch_message(event)
    elif event.post_type == "notice":
        await self._dispatch_notice(event)
    # ...
```

### 5.3 client.py — Action 发送器

**职责**：把 Action 对象序列化为 JSON 通过 WS 发送，管理 echo 配对。

```python
# 异步等待回包
response = await client.call(SendGroupMsgAction(group_id=123, message=[...]))
# response 是 dict: {"status": "ok", "data": {...}, "echo": "..."}

# 发送即忘（不等回包）
await client.send(SendGroupMsgAction(group_id=123, message=[...]))
```

### 5.4 config.py — 配置管理

**职责**：加载 TOML、提供类型安全的属性访问、支持热重载。

```python
from onebot_server import get_config

cfg = get_config("config.toml")
cfg.server_port          # → 8765
cfg.access_token         # → "你的token"
cfg.admin_qq             # → [10001, 10002]
cfg.ext_dir              # → "/绝对路径/.../extensions"
```

### 5.5 confirm.py — 敏感操作确认

详见第十一章。

### 5.6 whitelist.py — 白名单管理

详见第十二章。

---

## 第六章 Mixin 系统

### 6.1 什么是 Mixin

Mixin 是一种**多重继承**设计模式：每个 Mixin 类提供一组正交的功能，通过组合到 Handler 类上获得叠加效果。

```python
# 单个 Mixin
class LogMixin(BaseMixin):
    async def mixin_on_message(self, event, client):
        self.logger.info(f"收到消息: {event.get_message_text()}")

# 组合多个 Mixin
class Handler(LogMixin, BackupMixin, ConsoleMixin, TaskMixin, OneBotHandler):
    pass
```

### 6.2 内置 Mixin 一览

| Mixin | 文件 | 功能 |
|-------|------|------|
| LogMixin | `log_mixin.py` | 记录所有事件到日志 |
| BackupMixin | `backup_mixin.py` | 退群时自动备份白名单+群列表 |
| ConsoleMixin | `console_mixin.py` | 提供 CLI 命令（status/approve/reload） |
| TaskMixin | `task_mixin.py` | 定时任务调度 |
| StatsMixin | `stats_mixin.py` | 消息统计（可继承扩展） |

### 6.3 Mixin 生命周期钩子

每个 Mixin 可以定义以下钩子（全部可选）：

| 钩子方法 | 调用时机 | 参数 |
|----------|---------|------|
| `mixin_on_load(handler)` | Mixin 被组合到 Handler 时 | handler 实例 |
| `mixin_on_event(event)` | 每个事件到达时（总入口） | event 对象 |
| `mixin_on_message(event)` | 收到消息时 | MessageEvent |
| `mixin_on_group_message(event)` | 收到群消息时 | GroupMessageEvent |
| `mixin_on_private_message(event)` | 收到私聊时 | PrivateMessageEvent |
| `mixin_on_notice(event)` | 收到通知时 | NoticeEvent |
| `mixin_on_request(event)` | 收到请求时 | RequestEvent |
| `mixin_on_meta(event)` | 收到元事件时 | MetaEvent |
| `mixin_on_response(response)` | 收到 Action 回包时 | dict |
| `mixin_on_connect(client)` | WS 连接建立时 | OneBotClient |
| `mixin_on_disconnect(client)` | WS 连接断开时 | OneBotClient |

### 6.4 优先级规则

**MRO 中靠前的 Mixin 优先级更高（先执行）**。

```python
# 配置: auto_load = ["log_mixin", "backup_mixin", "console_mixin", "task_mixin"]
# 生成类: class DynamicHandler(LogMixin, BackupMixin, ConsoleMixin, TaskMixin, BaseMixin, OneBotHandler, object)
# MRO 顺序: LogMixin → BackupMixin → ConsoleMixin → TaskMixin → ...
# 执行顺序: LogMixin 先执行，TaskMixin 最后执行
```

如果 TaskMixin 的 `mixin_on_message` 返回了非 None 值，后面的 Mixin 就不会再收到该事件（短路机制）。

### 6.5 Mixin 之间的通信

Mixin 可以通过 `self`（即 Handler 实例）共享状态：

```python
class MyMixin(BaseMixin):
    async def mixin_on_load(self, handler):
        # 在 handler 上存共享数据
        handler.shared_data = {}
    
    async def mixin_on_message(self, event):
        # 读取其他 Mixin 写入的数据
        if hasattr(self, "shared_data"):
            self.shared_data["last_msg"] = event
```

### 6.6 Mixin 继承 Mixin（高级）

`stats_mixin.py` 演示了 Mixin 继承 Mixin：

```python
# stats_mixin.py
from ..mixin_base import BaseMixin

class StatsMixin(BaseMixin):
    """基础统计 Mixin"""
    def __init__(self):
        self._msg_count = 0
    
    async def mixin_on_message(self, event):
        self._msg_count += 1

class AdvancedStatsMixin(StatsMixin):
    """扩展统计 Mixin，继承基础统计"""
    def __init__(self):
        super().__init__()
        self._group_stats = {}
    
    async def mixin_on_message(self, event):
        await super().mixin_on_message(event)  # 调用父类统计
        if hasattr(event, "group_id"):
            gid = event.group_id
            self._group_stats[gid] = self._group_stats.get(gid, 0) + 1
```

---

## 第七章 Extension 系统

### 7.1 什么是 Extension

Extension 是**运行时可热加载的插件**，放在 `onebot_server/extensions/` 目录下，支持四种操作：

| 操作 | 方法 | 说明 |
|------|------|------|
| 冷加载 | `cold_load_all()` | 启动时扫描目录全部加载 |
| 热加载 | `hot_load(name)` | 运行时加载/重载单个 |
| 热卸载 | `hot_unload(name)` | 运行时卸载单个 |
| 冷卸载 | `cold_unload_all()` | 关闭时全部卸载 |
| 热重载 | `hot_reload(name)` | 卸载 + 重新加载 |

### 7.2 Extension 基类

所有插件必须继承 `BaseExtension`：

```python
# onebot_server/extension_base.py
class BaseExtension:
    """插件基类。所有插件必须继承此类。"""
    
    name: str = ""           # 插件名
    version: str = "1.0.0"  # 版本
    description: str = ""    # 描述
    priority: int = 100      # 优先级（越小越先执行）
    
    async def ext_load(self, handler) -> bool:
        """加载时调用。返回 False 表示加载失败。"""
        return True
    
    async def ext_unload(self) -> bool:
        """卸载时调用。清理资源。"""
        return True
    
    # 事件钩子（和 Mixin 类似但前缀是 on_）
    async def on_message(self, event, client):
        pass
    async def on_group_message(self, event, client):
        pass
    async def on_private_message(self, event, client):
        pass
    async def on_notice(self, event, client):
        pass
    async def on_request(self, event, client):
        pass
```

### 7.3 内置 Extension

| 插件 | 文件 | 功能 |
|------|------|------|
| Echo | `echo.py` | `/echo` 复读机 |
| AutoReply | `autoreply.py` | 关键词自动回复（配置驱动） |
| Moderation | `moderation.py` | 群管助手（禁言/踢人/退群，需审批） |
| Welcome | `welcome.py` | 入群欢迎语 |

### 7.4 热加载原理

```
用户修改 extensions/echo.py
        │
        ▼
ExtensionManager 文件监控（每 2 秒扫描 mtime）
        │
        ▼
检测到 mtime 变化 → hot_reload("echo")
        │
        ├── _unload_one("echo") → ext_unload() → 从 sys.modules 移除
        └── _load_one("echo") → importlib 重新导入 → ext_load()
```

### 7.5 Extension 的安全限制

Extension **不能直接操作 WebSocket**，只能通过以下安全接口：

```python
# ✅ 允许：通过 handler 的 client 发送
await self.handler.client.send_action(action)

# ✅ 允许：通过 safe_send 快捷方法
await self.safe_send_group_msg(group_id, "hello")
await self.safe_send_private_msg(user_id, "hi")

# ❌ 禁止：直接持有 WebSocket 引用
self._ws = websocket  # ExtensionManager 会警告

# ❌ 禁止：直接操作 Server
self._server = server  # 不在 Extension 能力范围内
```

---

## 第八章 事件模型

### 8.1 事件类型总览

| post_type | 说明 | 对应类 |
|-----------|------|--------|
| `message` | 消息事件 | `MessageEvent` → `GroupMessageEvent` / `PrivateMessageEvent` |
| `notice` | 通知事件 | `NoticeEvent` → `GroupNoticeEvent` |
| `request` | 请求事件 | `RequestEvent` → `GroupRequestEvent` / `FriendRequestEvent` |
| `meta_event` | 元事件 | `MetaEvent`（心跳/生命周期） |

### 8.2 群消息事件

```python
@dataclass
class GroupMessageEvent(MessageEvent):
    group_id: int           # 群号
    user_id: int            # 发送者 QQ
    message: List[MessageSegment]  # 消息段列表
    raw_message: str        # 原始消息字符串
    message_id: int         # 消息 ID
    sender: Sender          # 发送者信息
    anonymous: Optional[dict] = None  # 匿名信息
    
    def get_message_text(self) -> str:
        """提取纯文本内容。"""
        return "".join(
            seg.data.get("text", "")
            for seg in self.message
            if seg.type == "text"
        )
```

### 8.3 通知事件

| notice_type | 说明 |
|-------------|------|
| `group_ban` | 群禁言 |
| `group_decrease` | 群成员减少（退群/被踢） |
| `group_increase` | 群成员增加（入群） |
| `group_admin` | 管理员变更 |
| `group_upload` | 群文件上传 |
| `friend_add` | 好友添加 |

### 8.4 请求事件

| request_type | 说明 |
|--------------|------|
| `friend` | 加好友请求 |
| `group` | 加群请求 |

### 8.5 元事件

| meta_event_type | 说明 |
|-----------------|------|
| `heartbeat` | 心跳包（含 interval） |
| `lifecycle` | 生命周期（启停通知） |

### 8.6 事件解析示例

```python
from onebot_server.events import BaseEvent

raw = {
    "time": 1700000000, "self_id": 10000,
    "post_type": "message", "message_type": "group",
    "group_id": 12345, "user_id": 67890,
    "message": [{"type": "text", "data": {"text": "你好"}}],
    "raw_message": "你好", "message_id": 111,
    "sender": {"nickname": "张三", "role": "member"},
}

event = BaseEvent.from_dict(raw)
# event 自动转为 GroupMessageEvent
print(type(event).__name__)  # "GroupMessageEvent"
print(event.group_id)         # 12345
print(event.get_message_text())  # "你好"
```

---

## 第九章 Action API 大全

### 9.1 消息类

| Action 类 | action 名 | 参数 | 说明 |
|-----------|-----------|------|------|
| `SendGroupMsgAction` | `send_group_msg` | group_id, message | 发群消息 |
| `SendPrivateMsgAction` | `send_private_msg` | user_id, message | 发私聊 |
| `SendMsgAction` | `send_msg` | message_type, group_id/user_id, message | 通用发送 |

### 9.2 信息获取类

| Action 类 | action 名 | 参数 | 返回 |
|-----------|-----------|------|------|
| `GetLoginInfoAction` | `get_login_info` | — | 机器人自身信息 |
| `GetGroupListAction` | `get_group_list` | — | 群列表 |
| `GetGroupMemberListAction` | `get_group_member_list` | group_id | 群成员列表 |
| `GetGroupMemberInfoAction` | `get_group_member_info` | group_id, user_id | 单个成员信息 |
| `GetMsgAction` | `get_msg` | message_id | 消息详情 |
| `GetFriendListAction` | `get_friend_list` | — | 好友列表 |
| `GetVersionInfoAction` | `get_version_info` | — | LLOneBot 版本 |
| `GetStatusAction` | `get_status` | — | 连接状态 |

### 9.3 群管理类

| Action 类 | action 名 | 参数 | 说明 |
|-----------|-----------|------|------|
| `SetGroupBanAction` | `set_group_ban` | group_id, user_id, duration | 禁言 |
| `SetGroupWholeBanAction` | `set_group_whole_ban` | group_id, enable | 全员禁言 |
| `SetGroupKickAction` | `set_group_kick` | group_id, user_id, reject_add_request | 踢人 |
| `SetGroupLeaveAction` | `set_group_leave` | group_id, is_dismiss | 退群/解散 |
| `SetGroupAdminAction` | `set_group_admin` | group_id, user_id, enable | 设管理员 |
| `SetGroupCardAction` | `set_group_card` | group_id, user_id, card | 设群名片 |
| `SetGroupNameAction` | `set_group_name` | group_id, group_name | 改群名 |
| `SetGroupSpecialTitleAction` | `set_group_special_title` | group_id, user_id, special_title | 设专属头衔 |

### 9.4 请求处理类

| Action 类 | action 名 | 参数 | 说明 |
|-----------|-----------|------|------|
| `ApproveFriendRequestAction` | `set_friend_add_request` | flag, approve, remark | 处理加好友 |
| `ApproveGroupRequestAction` | `set_group_add_request` | flag, approve, reason | 处理加群 |

### 9.5 调用示例

```python
from onebot_server import OneBotClient
from onebot_server.actions import (
    SendGroupMsgAction, SetGroupBanAction,
    GetLoginInfoAction, build_message,
)
from onebot_server.segments import text, at, image

# 发送群消息
action = SendGroupMsgAction(
    group_id=12345,
    message=build_message(
        at(67890),
        " 你好！",
        image("http://example.com/pic.png"),
    ),
)
response = await client.call(action)
if response["status"] == "ok":
    print("发送成功")

# 禁言 10 分钟
ban = SetGroupBanAction(group_id=12345, user_id=67890, duration=600)
await client.send(ban)

# 获取登录信息
info = await client.call(GetLoginInfoAction())
print(info["data"]["nickname"])
```

---

## 第十章 消息段构造

### 10.1 函数式 API

```python
from onebot_server.segments import (
    text, image, at, reply, face, poke,
    record, video, share, location, forward,
    node, xml_message, json_message, build_message,
)

# 文本
text("hello")  # → {"type": "text", "data": {"text": "hello"}}

# 图片（URL / base64 / 本地文件）
image("http://example.com/a.png")
image("base64://iVBORw0KGgo...")  # 注意不带前缀会自动加
image("file:///path/to/local.png")

# @人
at(12345)       # @指定人
at("all")       # @全体成员

# 回复
reply(999)      # 回复消息 ID 999

# 表情
face(14)        # 微笑
face(76)        # 点赞

# 组合消息
build_message(text("hi "), at(123), text(" 看看这张图"), image("http://x.com/p.png"))
```

### 10.2 类式 API（链式调用）

```python
from onebot_server.segments import TextSegment, ImageSegment, AtSegment, ReplySegment, FaceSegment

# 文本
TextSegment.plain("hello")
TextSegment.format("hi {}!", "there")

# 图片
ImageSegment.from_url("http://example.com/a.png")
ImageSegment.from_base64("iVBORw0KGgo...")
ImageSegment.from_file("/path/to/image.png")

# @人
AtSegment.someone(12345)
AtSegment.all()
AtSegment.me(self_id=10000)

# 回复
ReplySegment.to(message_id=999)

# 表情预设
FaceSegment.smile    # 😊
FaceSegment.laugh    # 😄
FaceSegment.thumbs_up # 👍
```

### 10.3 消息段类型速查

| type | data 字段 | 说明 |
|------|-----------|------|
| text | text | 纯文本 |
| image | file, url?, cache | 图片 |
| face | id | QQ 表情 |
| at | qq, name? | @人 |
| reply | id | 引用回复 |
| record | file, url?, cache | 语音 |
| video | file, url?, cache | 视频 |
| poke | qq | 戳一戳 |
| share | url, title, content, image | 分享卡片 |
| location | lat, lon, title, content | 位置 |
| forward | id | 合并转发 |
| node | user_id, nickname, content | 转发节点 |
| xml | data | XML 消息 |
| json | data | JSON 消息 |

---

## 第十一章 敏感操作确认机制

### 11.1 为什么需要确认

退群、踢人、全员禁言等操作不可逆或影响大，需要**管理员二次确认**防止：
- 机器人被恶意利用
- 操作者手滑
- 插件逻辑 bug 导致误操作

### 11.2 工作流程

```
用户触发敏感操作（如发 /banme）
        │
        ▼
Extension 调用 ConfirmManager.submit()
        │
        ▼
生成唯一 token，记录请求详情
        │
        ▼
返回 token 给用户
        │
        ▼
管理员收到通知，执行 /approve <token>
        │
        ▼
ConfirmManager.approve(token, admin_id)
        │
        ├── 验证 admin_id 在白名单中
        ├── 验证 token 未过期
        └── 执行原始 Action
```

### 11.3 API 使用

```python
from onebot_server import ConfirmManager

cm = ConfirmManager(timeout=300)  # 5 分钟超时

# 提交确认请求
token = await cm.submit(
    action_type="set_group_ban",
    params={"group_id": 123, "user_id": 456, "duration": 600},
    description="禁言用户 456 (群123, 10分钟)",
    executor=789,  # 发起者 QQ
)

# 查看待审批列表
pending = await cm.list_pending()
# → [{"token": "...", "description": "...", "created_at": ..., "executor": ...}]

# 管理员批准
ok, msg = await cm.approve(token, admin_id=10001)
# ok=True 表示批准并执行成功

# 管理员拒绝
ok, msg = await cm.reject(token, admin_id=10001, reason="不合适")
```

### 11.4 在 Extension 中集成

```python
# extensions/moderation.py (简化)
from onebot_server.extension_base import BaseExtension
from onebot_server.actions import SetGroupBanAction
from onebot_server.segments import text

class ModerationExtension(BaseExtension):
    name = "moderation"
    description = "群管助手（敏感操作需审批）"
    
    async def on_group_message(self, event, client):
        text = event.get_message_text().strip()
        handler = self.handler
        
        if text == "/banme":
            # 提交确认请求
            token = await handler.confirm_manager.submit(
                action_type="set_group_ban",
                params={
                    "group_id": event.group_id,
                    "user_id": event.user_id,
                    "duration": 60,
                },
                description=f"禁言 {event.user_id} (60秒)",
                executor=event.user_id,
            )
            await client.send_action(SetGroupMsgAction(
                group_id=event.group_id,
                message=[text(f"已提交审批，token: {token[:8]}...")],
            ))
```

---

## 第十二章 白名单与备份

### 12.1 WhitelistManager

管理允许机器人操作的群和好友列表。

```python
from onebot_server import WhitelistManager

wm = WhitelistManager(data_dir="data")

# 添加
wm.add_group(12345)
wm.add_friend(67890)

# 检查
wm.is_group_whitelisted(12345)    # → True
wm.is_friend_whitelisted(99999)   # → False

# 移除
wm.remove_group(12345)
wm.remove_friend(67890)

# 群列表管理（非白名单，是已知群记录）
wm.update_group_list([111, 222, 333])
wm.list_groups()  # → [111, 222, 333]

# 导出/导入
exported = wm.export_all()
# → {"group_whitelist": [...], "friend_whitelist": [...], "group_list": [...]}
wm.import_groups([111, 222])
```

### 12.2 自动备份

BackupMixin 在检测到退群事件时自动备份：

```python
# backup_mixin.py 核心逻辑
async def mixin_on_notice(self, event):
    if event.notice_type == "group_decrease":
        if event.user_id == self.config.get("self_id", 0):
            # 自己被踢或主动退群 → 备份
            await self._backup_all()

async def _backup_all(self):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup = {
        "timestamp": timestamp,
        "group_whitelist": self.whitelist.export_all()["group_whitelist"],
        "group_list": self.whitelist.list_groups(),
    }
    filepath = Path(self.backup_dir) / f"backup_{timestamp}.json"
    filepath.write_text(json.dumps(backup, indent=2, ensure_ascii=False))
    self.logger.info(f"[Backup] 已备份到 {filepath}")
```

### 12.3 备份文件格式

```json
{
  "timestamp": "20250115_143022",
  "group_whitelist": [12345, 67890],
  "group_list": [12345, 67890, 11111]
}
```

---

## 第十三章 CLI 命令行

### 13.1 启动参数

```bash
python main.py [--config CONFIG] [--token TOKEN] [--host HOST] [--port PORT]
```

| 参数 | 说明 | 默认 |
|------|------|------|
| `--config` | TOML 配置文件路径 | `config.toml` |
| `--token` | 覆盖配置文件中的 access_token | 配置值 |
| `--host` | 覆盖监听地址 | 配置值 |
| `--port` | 覆盖监听端口 | 配置值 |

### 13.2 运行时命令

程序启动后，终端支持以下命令：

| 命令 | 说明 |
|------|------|
| `help` | 显示帮助 |
| `status` | 显示连接状态、已加载插件、待审批数 |
| `list` | 列出所有已加载插件 |
| `load <name>` | 热加载插件 |
| `unload <name>` | 热卸载插件 |
| `reload <name>` | 热重载插件 |
| `pending` | 列出待审批的敏感操作 |
| `approve <token>` | 批准一个请求 |
| `reject <token> [reason]` | 拒绝一个请求 |
| `backup` | 手动触发备份 |
| `quit` / `exit` | 优雅退出 |

### 13.3 控制台输出示例

```
> status
[状态] LLOneBot 已连接
[插件] 4 个已加载: echo, autoreply, moderation, welcome
[待审批] 1 个请求
[统计] 今日消息: 156 条

> pending
[1] token=a3f2... 禁言用户 456 (群123, 10分钟) - 由 789 发起

> approve a3f2
[✓] 已批准: 禁言用户 456 (群123, 10分钟)

> list
[1] echo v1.0.0 - 复读机 (priority=100)
[2] autoreply v1.0.0 - 关键词自动回复 (priority=100)
[3] moderation v1.0.0 - 群管助手 (priority=50)
[4] welcome v1.0.0 - 入群欢迎 (priority=200)
```

---

## 第十四章 日志系统

### 14.1 Loguru 封装

```python
from onebot_server import get_logger

logger = get_logger()
logger.info("普通信息")
logger.warning("警告")
logger.error("错误")
logger.debug("调试信息")
```

### 14.2 日志格式

控制台输出（彩色）：
```
2025-01-15 14:30:22 | INFO     | onebot_server.server:start:205 - WebSocket 服务已就绪
2025-01-15 14:30:25 | WARNING  | onebot_server.handler:handle_event:88 - 未知事件类型: weird_type
2025-01-15 14:30:30 | ERROR    | onebot_server.extension_manager:_load_one:236 - 加载 echo 失败: SyntaxError
```

### 14.3 文件轮转

```toml
[logging]
log_dir = "logs"
max_size = 10      # 单文件 10MB
retention = 30      # 保留 30 个文件
```

超过 10MB 自动切割为 `bot_2025-01-15_1.log`、`bot_2025-01-15_2.log`...

---

## 第十五章 自定义 Mixin 教程

### 15.1 创建文件

在 `onebot_server/mixin/` 目录下新建 `my_mixin.py`：

```python
"""
my_mixin.py — 自定义 Mixin 示例
=================================
功能：记录每个群的消息频率，超过阈值告警。
"""

from __future__ import annotations
import time
from collections import defaultdict
from typing import Any, Dict

from ..mixin_base import BaseMixin
from ..logger import get_logger

logger = get_logger()

class RateLimitMixin(BaseMixin):
    """
    消息频率限制 Mixin。
    当某个群在 60 秒内超过 30 条消息时触发告警。
    """
    
    # Mixin 配置
    WINDOW_SECONDS: int = 60
    MAX_MESSAGES: int = 30
    
    def __init__(self):
        super().__init__()
        self._msg_times: Dict[int, list] = defaultdict(list)
    
    async def mixin_on_load(self, handler):
        logger.info("[RateLimit] Mixin 已加载")
    
    async def mixin_on_group_message(self, event):
        gid = event.group_id
        now = time.time()
        window_start = now - self.WINDOW_SECONDS
        
        # 清理过期记录
        self._msg_times[gid] = [
            t for t in self._msg_times[gid] if t > window_start
        ]
        
        # 添加当前消息
        self._msg_times[gid].append(now)
        
        # 检查是否超限
        count = len(self._msg_times[gid])
        if count == self.MAX_MESSAGES:
            logger.warning(
                f"[RateLimit] 群 {gid} 消息频率过高: {count}/{self.WINDOW_SECONDS}s"
            )
            # 可以通过 handler.client 发送告警
            if hasattr(self, "client") and self.client:
                from ..actions import SendGroupMsgAction
                from ..segments import text
                await self.client.send_action(SendGroupMsgAction(
                    group_id=gid,
                    message=[text("⚠️ 消息频率过高，请注意！")],
                ))
    
    async def mixin_on_unload(self):
        logger.info("[RateLimit] Mixin 已卸载")
        self._msg_times.clear()
```

### 15.2 注册到配置

编辑 `config.toml`：

```toml
[mixin]
auto_load = [
    "log_mixin",
    "backup_mixin",
    "console_mixin",
    "task_mixin",
    "my_mixin",    # ← 新增
]
```

重启服务即可生效。

### 15.3 Mixin 继承 Mixin

```python
# onebot_server/mixin/advanced_rate_limit.py
"""
继承 RateLimitMixin，增加：
- 按用户统计
- 超限自动禁言
"""

from .my_mixin import RateLimitMixin
from ..actions import SetGroupBanAction

class AdvancedRateLimitMixin(RateLimitMixin):
    """高级频率限制：超限自动禁言 5 分钟。"""
    
    BAN_DURATION: int = 300  # 5 分钟
    
    def __init__(self):
        super().__init__()
        self._user_counts: dict = defaultdict(int)
    
    async def mixin_on_group_message(self, event):
        # 先调用父类逻辑
        await super().mixin_on_group_message(event)
        
        # 额外：按用户统计
        uid = event.user_id
        self._user_counts[uid] += 1
        
        if self._user_counts[uid] > 50:
            # 自动禁言
            if hasattr(self, "client") and self.client:
                await self.client.send_action(SetGroupBanAction(
                    group_id=event.group_id,
                    user_id=uid,
                    duration=self.BAN_DURATION,
                ))
                self._user_counts[uid] = 0
```

---

## 第十六章 自定义 Extension 教程

### 16.1 最简插件

在 `onebot_server/extensions/` 下新建 `hello.py`：

```python
"""
hello.py — 最简单的插件
========================
功能：回复 /hello 命令
"""

from typing import Optional
from onebot_server.extension_base import BaseExtension
from onebot_server.events import GroupMessageEvent
from onebot_server.segments import text, build_message

class HelloExtension(BaseExtension):
    name = "hello"
    version = "1.0.0"
    description = "回复 /hello"
    priority = 100
    
    async def on_group_message(self, event: GroupMessageEvent, client) -> Optional[dict]:
        msg_text = event.get_message_text().strip()
        
        if msg_text == "/hello":
            from onebot_server.actions import SendGroupMsgAction
            await client.send_action(SendGroupMsgAction(
                group_id=event.group_id,
                message=build_message(text("Hello, World! 🌍")),
            ))
            return {"handled": True}  # 短路，不再传给其他插件
        
        return None  # 继续传递给下一个插件
```

保存文件 → 自动热加载 → 群内 `/hello` 即可看到回复。

### 16.2 使用 safe_send 快捷方法

```python
class MyExt(BaseExtension):
    async def on_group_message(self, event, client):
        # 方式 1：通过 client（需 import Action 类）
        from onebot_server.actions import SendGroupMsgAction
        await client.send_action(SendGroupMsgAction(
            group_id=event.group_id,
            message=[{"type": "text", "data": {"text": "hi"}}],
        ))
        
        # 方式 2：通过 safe_send（Extension 基类提供）
        await self.safe_send_group_msg(event.group_id, "hi")
        await self.safe_send_private_msg(event.user_id, "私聊 hi")
```

### 16.3 带配置的插件

```python
"""
weather.py — 天气查询插件（演示配置读取）
"""

import json
from pathlib import Path
from onebot_server.extension_base import BaseExtension

class WeatherExtension(BaseExtension):
    name = "weather"
    version = "1.0.0"
    description = "天气查询 /weather 城市名"
    
    def __init__(self):
        super().__init__()
        self.api_key = ""
        self.city_map = {}
    
    async def ext_load(self, handler) -> bool:
        # 从 handler 读取配置
        config = handler.config
        self.api_key = config.get("weather.api_key", "")
        
        # 加载城市映射
        city_file = Path(__file__).parent / "weather_cities.json"
        if city_file.exists():
            self.city_map = json.loads(city_file.read_text())
        
        return True if self.api_key else False
    
    async def on_group_message(self, event, client):
        text = event.get_message_text().strip()
        if text.startswith("/weather"):
            city = text.replace("/weather", "").strip()
            if not city:
                await self.safe_send_group_msg(event.group_id, "用法: /weather 北京")
                return {"handled": True}
            
            # 这里调用天气 API...
            await self.safe_send_group_msg(event.group_id, f"{city}: 晴 25°C")
            return {"handled": True}
```

### 16.4 Extension 安全规则

| 可以做 ✅ | 不可以做 ❌ |
|-----------|-----------|
| 继承 BaseExtension | 继承 OneBotServer |
| 用 `self.handler.client` 发消息 | 直接持有 WebSocket 对象 |
| 用 `self.handler.config` 读配置 | 修改 handler 核心属性 |
| 用 `self.safe_send_*` 快捷发送 | 直接操作 ExtensionManager |
| 在 `ext_load` 中初始化资源 | 在模块顶层做重操作 |
| 读写自己目录下的文件 | 删除/修改其他插件文件 |

---

## 第十七章 LLOneBot 对接指南

### 17.1 安装 LLOneBot

1. 安装最新 NTQQ 并登录（只登 1 个号）
2. 安装 LiteLoaderQQNT
3. 下载 LLOneBot 插件包（带 ffmpeg 版）
4. QQ → 设置 → LiteLoaderQQNT → 安装插件 → 选 zip
5. 重启 QQ，设置里出现 LLOneBot 选项卡

### 17.2 配置反向 WS

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 启用反向 WS | ✅ | 打开开关 |
| WS 地址 | `ws://127.0.0.1:8765/` | 本程序地址+端口 |
| Access Token | 和 config.toml 一致 | 鉴权令牌 |
| 消息格式 | 消息段 | 选「消息段」不选 CQ 码 |
| 心跳间隔 | 30000 | 30 秒，和本程序 heartbeat_timeout 匹配 |

### 17.3 验证连接

1. 启动本程序：`python main.py`
2. 在 QQ 设置里点「应用并重启服务」
3. 观察本程序日志：

```
[Server] 新连接来自 ('127.0.0.1', 54321)
[Handler] LLOneBot 已连接
[Handler] 收到元事件: lifecycle
```

4. 群内 `@机器人 /echo 测试` → 复读成功即全链路通

### 17.4 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 连接立即断开 | Token 不匹配 | 两边 Token 改一致 |
| 连接成功但收不到消息 | 消息格式选了 CQ 码 | 改为「消息段」 |
| 间歇性断连 | 心跳超时太短 | 调大 heartbeat_timeout |
| 发消息报错 | Action 参数错 | 检查 group_id/user_id 类型 |
| 插件不生效 | 文件放错目录 | 确认在 `onebot_server/extensions/` |

---

## 第十八章 测试

### 18.1 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio

# 运行全部测试
python -m pytest tests/test_all.py -v

# 运行指定类别
python -m pytest tests/test_all.py::TestConfig -v
python -m pytest tests/test_all.py::TestExtensionManager -v

# 带覆盖率
pip install pytest-cov
python -m pytest tests/test_all.py --cov=onebot_server --cov-report=term-missing
```

### 18.2 测试覆盖内容

| 测试类 | 覆盖内容 | 用例数 |
|--------|---------|--------|
| TestConfig | TOML 加载、嵌套取值、路径解析 | 5 |
| TestEvents | 5 种事件类型解析 | 6 |
| TestActions | 6 种 Action 序列化 | 6 |
| TestSegments | 消息段构造（函数式+类式） | 9 |
| TestMixinSystem | Mixin 加载、继承、优先级 | 8 |
| TestExtensionManager | 冷/热加载、卸载、重载 | 5 |
| TestConfirmManager | 提交、批准、拒绝、过期 | 4 |
| TestWhitelist | 增删查、持久化、导入导出 | 5 |
| TestServerIntegration | 服务器初始化、事件分发 | 4 |
| TestEndToEnd | 完整流程模拟 | 4 |

### 18.3 预期结果

```
======================== 55 passed, 2 warnings in 3.31s ====================
```

> 2 个 warning 来自 `websockets` 库自身的 deprecation，非本项目问题。

---

## 第十九章 故障排查

### 19.1 启动失败

**问题**：`ImportError: attempted relative import with no known parent package`

→ 原因：直接运行了 `onebot_server/` 下的文件
→ 解决：从项目根目录运行 `python main.py`，确保 `onebot_server` 作为包被导入

**问题**：`OSError: [Errno 98] Address already in use`

→ 原因：8765 端口被占用
→ 解决：改 `config.toml` 的 `server.port`，或 `lsof -i:8765` 找到占用进程

### 19.2 连接问题

**问题**：LLOneBot 连不上，日志无输出

→ 检查：防火墙是否放行端口
→ 检查：`config.toml` 的 `host` 是否绑对网卡
→ 检查：LLOneBot 的 WS 地址是否 `ws://` 开头（不是 `http://`）

**问题**：`鉴权失败，关闭连接`

→ 检查：LLOneBot 的 Token 和 `config.toml` 的 `access_token` 是否完全一致
→ 检查：Token 是否有多余空格/换行

### 19.3 消息问题

**问题**：收到消息但 Extension 没反应

→ 检查：Extension 是否成功加载（`list` 命令查看）
→ 检查：消息格式是否「消息段」（不是 CQ 码）
→ 检查：Extension 的 `on_group_message` 是否写了 `return {"handled": True}` 导致短路

**问题**：发送消息报 `echo timeout`

→ 原因：LLOneBot 没回包
→ 检查：LLOneBot 是否正常运行
→ 调大：`config.toml` 的 `action_timeout`

### 19.4 插件问题

**问题**：修改插件后没生效

→ 检查：`hot_reload` 是否为 `true`
→ 检查：文件是否在 `onebot_server/extensions/` 下
→ 手动：`reload <name>` 命令强制重载

**问题**：插件加载报错 `未找到 BaseExtension 子类`

→ 检查：插件类是否继承了 `BaseExtension`
→ 检查：类名是否和文件名不同导致没被识别

---

## 第二十章 API 速查表

### 20.1 核心导入

```python
# 一站式导入
from onebot_server import (
    OneBotServer, OneBotHandler, OneBotClient,
    Config, get_config, get_logger,
    BaseEvent, GroupMessageEvent, PrivateMessageEvent,
    BaseAction, BaseExtension, BaseMixin,
    ExtensionManager, ConfirmManager, WhitelistManager,
    build_message, text, image, at, reply, face,
)

# 或全部导入
from onebot_server import *
```

### 20.2 事件类型速查

| 事件 | post_type | 子类型字段 | 关键属性 |
|------|-----------|-----------|---------|
| 群消息 | message | message_type=group | group_id, user_id, message, raw_message |
| 私聊 | message | message_type=private | user_id, message |
| 群禁言 | notice | notice_type=group_ban | group_id, user_id, duration |
| 群成员减少 | notice | notice_type=group_decrease | group_id, user_id, operator_id |
| 群成员增加 | notice | notice_type=group_increase | group_id, user_id, operator_id |
| 加好友 | request | request_type=friend | user_id, comment, flag |
| 加群 | request | request_type=group | group_id, user_id, comment, flag |
| 心跳 | meta_event | meta_event_type=heartbeat | interval |

### 20.3 Action 调用速查

```python
# 发群消息
SendGroupMsgAction(group_id=int, message=List[dict])

# 发私聊
SendPrivateMsgAction(user_id=int, message=List[dict])

# 禁言
SetGroupBanAction(group_id=int, user_id=int, duration=int)

# 踢人
SetGroupKickAction(group_id=int, user_id=int, reject_add_request=bool)

# 退群
SetGroupLeaveAction(group_id=int, is_dismiss=bool)

# 设管理员
SetGroupAdminAction(group_id=int, user_id=int, enable=bool)

# 获取登录信息
GetLoginInfoAction()

# 获取群列表
GetGroupListAction()

# 获取群成员
GetGroupMemberListAction(group_id=int)

# 获取消息详情
GetMsgAction(message_id=int)
```

### 20.4 消息段速查

```python
text("字符串")
image("url或base64或file://路径")
at(QQ号或"all")
reply(消息ID)
face(表情ID)
record("语音文件")
video("视频文件")
poke(QQ号)
share(url, title, content, image)
location(lat, lon, title, content)
build_message(seg1, seg2, ...)
```

### 20.5 配置属性速查

```python
cfg.server_host           # 监听地址
cfg.server_port           # 监听端口
cfg.server_path           # WS 路径
cfg.access_token          # 鉴权令牌
cfg.heartbeat_timeout     # 心跳超时
cfg.action_timeout        # Action 超时
cfg.log_level             # 日志级别
cfg.log_dir               # 日志目录
cfg.admin_qq              # 管理员列表
cfg.confirm_timeout       # 确认超时
cfg.backup_dir            # 备份目录
cfg.ext_dir               # 插件目录（绝对路径）
cfg.hot_reload            # 是否热加载
cfg.watch_interval        # 监控间隔
cfg.mixin_dir             # Mixin 目录（绝对路径）
cfg.auto_load_mixins      # 自动加载的 Mixin 列表
```

---

## 附录 文件清单

```
onebot11_server/
├── main.py                      # 主入口（启动脚本）
├── config.toml                  # TOML 主配置文件
├── requirements.txt             # Python 依赖（仅 2 个）
├── pyproject.toml              # 项目元信息 + pytest 配置
├── README.md                    # 快速入门（英文）
├── DOCUMENTATION.md             # 本文件（中文超长文档）
│
├── onebot_server/               # ⭐ 核心包（不可随意移动）
│   ├── __init__.py             # 统一导出
│   ├── config.py               # TOML 配置管理 + 路径解析
│   ├── logger.py               # Loguru 封装
│   ├── client.py               # WebSocket 客户端（Action 发送器）
│   ├── events.py               # 12 种事件模型 + from_dict 分发
│   ├── actions.py              # 20+ Action API + 消息段
│   ├── segments.py             # 消息段构造器（函数式 + 类式）
│   ├── confirm.py              # 敏感操作确认管理器
│   ├── whitelist.py            # 白名单 + 群列表管理
│   ├── extension_base.py       # Extension 基类
│   ├── extension_manager.py    # 热加载/卸载/重载
│   ├── handler.py              # 事件枢纽 + Mixin 代理
│   ├── server.py               # WebSocket 服务器 + CLI
│   └── mixin/                 # ⭐ Mixin 目录
│       ├── __init__.py
│       ├── log_mixin.py        # 日志 Mixin
│       ├── backup_mixin.py     # 备份 Mixin（退群自动备份）
│       ├── console_mixin.py    # 控制台 Mixin（CLI 命令）
│       ├── task_mixin.py       # 定时任务 Mixin
│       └── stats_mixin.py      # 统计 Mixin（继承示范）
│
├── extensions/                  # ⭐ 用户插件目录（热加载）
│   ├── echo.py                 # 复读机
│   ├── autoreply.py            # 关键词自动回复
│   ├── moderation.py           # 群管助手（需审批）
│   ├── welcome.py              # 入群欢迎
│   └── autoreply.json          # 自动回复规则配置
│
├── tests/                       # 测试套件
│   └── test_all.py             # 55 项综合测试
│
├── data/                        # 运行时数据（自动创建）
│   ├── group_whitelist.json    # 群白名单
│   ├── friend_whitelist.json   # 好友白名单
│   └── group_list.json         # 群列表
│
├── backups/                     # 备份目录（自动创建）
│   └── backup_YYYYMMDD_HHmmss.json
│
└── logs/                        # 日志目录（自动创建）
    └── bot_YYYY-MM-DD_N.log
```

---

> 📝 **最后更新**：2025-01-15
> 📮 **问题反馈**：查看代码注释或提交 Issue
> 🎯 **设计理念**：轻量、透明、可热更新、安全第一
