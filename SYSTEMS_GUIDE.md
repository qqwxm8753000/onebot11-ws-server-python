# OneBot 11 Server — 各系统完全讲解

> 本文档逐一拆解项目的 **12 个核心系统**，讲清楚每个系统是什么、做什么、怎么用、和谁交互。
> 适合已经跑通项目、想深入理解架构的开发者。

---

## 目录

1. [配置系统（Config）](#1-配置系统config)
2. [日志系统（Logger）](#2-日志系统logger)
3. [事件系统（Events）](#3-事件系统events)
4. [动作系统（Actions）](#4-动作系统actions)
5. [消息段系统（Segments）](#5-消息段系统segments)
6. [客户端系统（Client）](#6-客户端系统client)
7. [服务器系统（Server）](#7-服务器系统server)
8. [处理器系统（Handler）](#8-处理器系统handler)
9. [Mixin 系统](#9-mixin-系统)
10. [Extension 系统](#10-extension-系统)
11. [确认管理系统（Confirm）](#11-确认管理系统confirm)
12. [白名单系统（Whitelist）](#12-白名单系统whitelist)
13. [系统协作全景图](#13-系统协作全景图)
14. [数据流向：一条消息的旅程](#14-数据流向一条消息的旅程)

---

## 1. 配置系统（Config）

### 1.1 它是什么

项目的"控制中心"。所有可调参数（端口、Token、日志级别、管理员列表等）都集中在 `config.toml` 一个文件里，由 `config.py` 负责加载和读取。

### 1.2 配置文件结构

```toml
[server]       # WebSocket 服务器参数
[logging]     # 日志行为
[admin]        # 管理员与审批
[backup]      # 自动备份
[extension]   # 插件系统
[mixin]       # Mixin 加载列表
```

### 1.3 代码中的使用方式

```python
from onebot_server import get_config

config = get_config("config.toml")

# 读取
port = config.server_port           # → 8765
token = config.access_token        # → "change-me-to-a-random-token"
admins = config.admin_qq           # → [10001, 10002]

# 运行时修改（命令行覆盖场景）
config.set("server.port", 8080)

# 读任意路径
level = config.get("logging.level", "INFO")
```

### 1.4 关键设计点

| 特性 | 说明 |
|------|------|
| **单例模式** | `get_config()` 全局只创建一个实例，避免重复读盘 |
| **命令行覆盖** | `main.py` / `server.py` 的 CLI 参数可覆盖 TOML 值 |
| **支持热重载** | 部分项（如 `extension.hot_reload`）运行时可改 |
| **默认值兜底** | `config.get("xxx", default)` 防止 Key 不存在崩溃 |

### 1.5 和其他系统的关系

```
config.toml ──→ Config 单例 ──→ 所有系统读取参数
                                    ├── Server（host/port/token）
                                    ├── Logger（level/dir/max_size）
                                    ├── ConfirmManager（timeout）
                                    ├── WhitelistManager（data_dir）
                                    ├── ExtensionManager（ext_dir/watch_interval）
                                    └── 所有 Mixin（通过 handler.config 访问）
```

---

## 2. 日志系统（Logger）

### 2.1 它是什么

基于 **Loguru** 封装的统一日志模块。所有 `.py` 文件都通过 `from .logger import get_logger` 拿到同一个 logger 实例。

### 2.2 两种输出通道

| 通道 | 去向 | 格式 | 适用场景 |
|------|------|------|---------|
| **控制台** | stderr | 彩色、带时间 | 开发调试 |
| **文件** | `logs/onebot_YYYY-MM-DD.log` | 纯文本、按大小轮转 | 生产环境追溯 |

### 2.3 初始化时机

日志在 `Server.__init__()` 里初始化，**早于一切**：

```python
# server.py 中的初始化顺序
self.config = get_config(config_path)          # 1. 先读配置
init_logger(                                    # 2. 再初始化日志
    level=self.config.log_level,
    log_dir=self.config.log_dir,
    console=self.config.log_console,
    max_size=self.config.log_max_size,
    retention=self.config.log_retention,
)
self.logger = get_logger()                      # 3. 拿到 logger
```

> ⚠️ **为什么顺序重要**：如果先 import 其他模块、那些模块在顶层调用 `get_logger()`，此时 logger 还没初始化，会拿到一个未配置的默认 logger。

### 2.4 在插件中使用

```python
from onebot_server import get_logger

logger = get_logger()
logger.info("普通信息")
logger.debug("调试细节")
logger.warning("需要注意")
logger.error("出错了！")
```

### 2.5 日志轮转策略

```
logs/
├── onebot_2026-08-17.log   ← 今天的
├── onebot_2026-08-16.log   ← 昨天的
├── onebot_2026-08-15.log
└── ...共保留 30 个文件（retention=30）
    每个文件最大 10MB（max_size=10），超过就切新文件
```

---

## 3. 事件系统（Events）

### 3.1 它是什么

把 LLOneBot 发来的 **原始 JSON 字典** 转换成 **强类型的 Python dataclass 对象**。这是整个项目的"数据入口"。

### 3.2 事件分类体系

```
BaseEvent（基类，所有事件的根）
├── MessageEvent（消息事件）
│   ├── GroupMessageEvent    ← 群消息
│   └── PrivateMessageEvent  ← 私聊消息
├── NoticeEvent（通知事件）
│   └── GroupNoticeEvent     ← 群通知（退群/加群/禁言/撤回等）
├── RequestEvent（请求事件）
│   ├── GroupRequestEvent    ← 加群请求
│   └── FriendRequestEvent   ← 加好友请求
├── MetaEvent（元事件）
│   └── Heartbeat / Lifecycle ← 心跳 / 生命周期
└── UnknownEvent（兜底）
    └── 无法识别的事件原样保留
```

### 3.3 自动分发机制

`BaseEvent.from_dict(data)` 根据 `post_type` 字段**自动构造对应子类**：

```python
# events.py 核心分发逻辑
BaseEvent.register("message")(MessageEvent)
BaseEvent.register("notice")(NoticeEvent)
BaseEvent.register("request")(RequestEvent)
BaseEvent.register("meta_event")(MetaEvent)

# 使用时
event = BaseEvent.from_dict(raw_json_dict)
# post_type="message"  → 返回 GroupMessageEvent 或 PrivateMessageEvent
# post_type="notice"   → 返回 GroupNoticeEvent
# post_type="request"  → 返回 GroupRequestEvent / FriendRequestEvent
```

### 3.4 常用事件字段速查

#### 群消息 `GroupMessageEvent`

| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | int | 时间戳 |
| `self_id` | int | 机器人 QQ |
| `group_id` | int | 群号 |
| `user_id` | int | 发送者 QQ |
| `message` | list[MessageSegment] | 消息段列表 |
| `raw_message` | str | 原始文本 |
| `sender.nickname` | str | 发送者昵称 |
| `sender.card` | str | 群名片 |
| `sender.role` | str | owner/admin/member |
| `anonymous` | Anonymous \| None | 是否匿名 |

#### 群通知 `GroupNoticeEvent`

| `notice_type` | 含义 | 关键字段 |
|---------------|------|---------|
| `group_increase` | 有人入群 | `group_id`, `user_id`, `operator_id` |
| `group_decrease` | 有人退群/被踢 | `group_id`, `user_id`, `operator_id` |
| `group_ban` | 禁言/解禁 | `group_id`, `user_id`, `duration` |
| `group_recall` | 撤回消息 | `group_id`, `message_id` |

### 3.5 消息段解析

```python
# 原始消息是列表，每个元素是 {"type": "text", "data": {...}}
event.message  →  [MessageSegment(type="text", data={"text": "你好"}),
                   MessageSegment(type="at", data={"qq": "123456"})]

# 快速提取纯文本
text = event.get_message_text()  # → "你好"

# 遍历消息段
for seg in event.message:
    if seg.type == "text":
        print(seg.data["text"])
    elif seg.type == "at":
        print(f"@了 {seg.data['qq']}")
    elif seg.type == "image":
        print(f"图片: {seg.data.get('file', '')}")
```

---

## 4. 动作系统（Actions）

### 4.1 它是什么

和 Events 对称的另一端——**从机器人发往 LLOneBot 的指令**。每个 Action 对应一个 OneBot 11 API。

### 4.2 Action 分类一览

| 类别 | Action 类 | 对应 API | 用途 |
|------|-----------|---------|------|
| **发送消息** | `SendGroupMsgAction` | `send_group_msg` | 发群消息 |
| | `SendPrivateMsgAction` | `send_private_msg` | 发私聊 |
| | `SendMsgAction` | `send_msg` | 通用发送 |
| **查询信息** | `GetLoginInfoAction` | `get_login_info` | 获取机器人自身信息 |
| | `GetGroupListAction` | `get_group_list` | 获取群列表 |
| | `GetGroupMemberListAction` | `get_group_member_list` | 群成员列表 |
| | `GetGroupMemberInfoAction` | `get_group_member_info` | 单个成员信息 |
| | `GetFriendListAction` | `get_friend_list` | 好友列表 |
| | `GetMsgAction` | `get_msg` | 获取历史消息 |
| | `GetVersionInfoAction` | `get_version_info` | 版本信息 |
| | `GetStatusAction` | `get_status` | 连接状态 |
| **群管理** | `SetGroupBanAction` | `set_group_ban` | 禁言 |
| | `SetGroupWholeBanAction` | `set_group_whole_ban` | 全员禁言 |
| | `SetGroupKickAction` | `set_group_kick` | 踢人 |
| | `SetGroupLeaveAction` | `set_group_leave` | 退群 |
| | `SetGroupAdminAction` | `set_group_set_admin` | 设管理员 |
| | `SetGroupCardAction` | `set_group_card` | 改群名片 |
| | `SetGroupNameAction` | `set_group_name` | 改群名 |
| | `SetGroupSpecialTitleAction` | `set_group_special_title` | 设专属头衔 |
| **请求处理** | `ApproveFriendRequestAction` | `set_friend_add_request` | 同意/拒绝加好友 |
| | `ApproveGroupRequestAction` | `set_group_add_request` | 同意/拒绝加群 |

### 4.3 使用方式

```python
from onebot_server import SendGroupMsgAction, build_message

# 构造 Action
action = SendGroupMsgAction(
    group_id=123456,
    message=build_message("你好", at_segment(789)),  # 文本 + @某人
)

# 发送（不等回包）
echo = await client.send(action)

# 发送并等回包
resp = await client.call(action)
if resp.ok:
    print("发送成功", resp.data)
else:
    print("发送失败", resp.message)
```

### 4.4 ActionResponse 结构

```python
@dataclass
class ActionResponse:
    status: str       # "ok" / "failed"
    retcode: int      # 0=成功，非0=失败码
    data: dict        # API 返回的数据
    echo: str         # 对应的 echo 标识
    message: str      # 错误描述

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.retcode == 0
```

### 4.5 echo 配对机制

每个 Action 自动生成唯一 `echo`（UUID），LLOneBot 回包时原样返回，Client 用它匹配对应的 `Future`：

```
发送:  {"action": "send_group_msg", "params": {...}, "echo": "abc-123"}
                                                          ↓
回包:  {"status": "ok", "retcode": 0, "data": {...}, "echo": "abc-123"}
                                                          ↓
Client 找到 echo="abc-123" 的 Future → set_result(response)
```

---

## 5. 消息段系统（Segments）

### 5.1 它是什么

构造发送给 QQ 的消息内容的工具函数集合。OneBot 11 的消息不是纯文本，而是**消息段数组**。

### 5.2 快速构造工具

```python
from onebot_server import (
    text_segment, image_segment, at_segment,
    face_segment, reply_segment, build_message
)

# 纯文本
build_message("你好世界")

# 文本 + @某人 + 表情
build_message(
    text_segment("来看这个"),
    at_segment(123456),
    face_segment(14),  # 😄 笑脸
)

# 引用回复 + 图片
build_message(
    reply_segment(message_id=789),
    image_segment("https://example.com/pic.jpg"),
)
```

### 5.3 支持的消息段类型

| 类型 | 构造方式 | 说明 |
|------|---------|------|
| 文本 | `text_segment("内容")` | 纯文字 |
| 图片 | `image_segment(url)` | 支持 URL / base64 / 文件路径 |
| @某人 | `at_segment(123456)` | `at_segment("all")` = @全体成员 |
| 表情 | `face_segment(14)` | QQ 表情 ID |
| 回复 | `reply_segment(msg_id)` | 引用某条消息 |
| 语音 | `record_segment(file)` | 语音消息 |
| 视频 | `video_segment(file)` | 视频消息 |

### 5.4 面向对象风格（带预设表情）

```python
from onebot_server.segments import FaceSegment, AtSegment

FaceSegment.smile    # → face id=14（笑脸）
FaceSegment.laugh    # → face id=27（大笑）
FaceSegment.thumbs_up # → face id=76（👍）
FaceSegment.slap     # → face id=78（拍）
FaceSegment.shrug    # → face id=102（耸肩）

AtSegment.someone(123456)  # → @某人
AtSegment.all()            # → @全体成员
AtSegment.me(self_id)      # → @机器人自己
```

---

## 6. 客户端系统（Client）

### 6.1 它是什么

`OneBotClient` 是**单条 WebSocket 连接的封装**。它绑定一个已建立的 WebSocket，负责：
- 把 Action 对象序列化为 JSON 发出去
- 把收到的回包反序列化为 ActionResponse
- 用 echo 配对请求和响应
- 提供所有 Action 的快捷方法

### 6.2 生命周期

```
Server 启动
  ↓
等待 LLOneBot 连接
  ↓
_accept_connection(websocket)
  ↓
创建 OneBotClient(websocket, self_id)
  ↓
client.call/send  ←── Handler / Mixin / Extension 调用
  ↓
连接断开 → client.close() → 取消所有 pending Future
```

### 6.3 核心方法

| 方法 | 是否等待回包 | 返回值 | 用途 |
|------|:---:|------|------|
| `client.send(action)` | ❌ | `echo: str` | 发完就走，不关心结果 |
| `client.call(action)` | ✅ | `ActionResponse` | 等 LLOneBot 处理完 |
| `client.close()` | — | `None` | 关闭连接，清理 pending |

### 6.4 快捷方法（不用手动构造 Action）

```python
# 这些都在 client.py 里定义，直接调用即可
await client.send_group_msg(group_id, message)
await client.send_private_msg(user_id, message)
await client.set_group_ban(group_id, user_id, duration)
await client.set_group_kick(group_id, user_id)
await client.set_group_leave(group_id)
```

### 6.5 并发安全设计

```python
# client.py 内部
self._write_lock = asyncio.Lock()   # 写锁：保证 send 串行化
self._pending: Dict[str, Future] = {}  # echo → Future 映射

async def send(self, action):
    async with self._write_lock:    # ← 同一时刻只有一个协程在写 WS
        await self._ws.send(payload)
```

> WebSocket 连接不能并发写入，写锁确保多个 Mixin/Extension 同时发消息时不会交错。

### 6.6 在插件中获取 Client

```python
# Extension 中
async def ext_on_connect(self, client):
    self._client = client  # 保存引用

async def ext_on_message(self, event):
    await self.client.send_group_msg(event.group_id, build_message("hi"))
```

---

## 7. 服务器系统（Server）

### 7.1 它是什么

`OneBotServer` 是**整个应用的容器和启动入口**。它把配置、日志、白名单、确认管理器、Mixin、Extension 全部组装起来，启动 WebSocket 服务。

### 7.2 启动流程（完整时序）

```
python main.py
  │
  ▼
main.py: create_server()
  │  ├── 解析 CLI 参数
  │  ├── 加载 config.toml
  │  ├── 命令行覆盖配置
  │  └── 创建 OneBotServer
  ▼
OneBotServer.__init__()
  │  ├── get_config() → Config 单例
  │  ├── init_logger() → 日志就绪
  │  ├── ConfirmManager(timeout=300)
  │  ├── WhitelistManager(data_dir="data")
  │  ├── _load_mixin_list() → 从 config 读 auto_load
  │  └── create_handler_class(mixins) → 动态生成 Handler 类
  ▼
server.run_forever()
  │  ├── ExtensionManager.cold_load_all() → 加载所有插件
  │  ├── handler.mixin_setup_all() → 所有 Mixin 初始化
  │  ├── websockets.serve(_accept_connection, host, port)
  │  └── asyncio.run() → 事件循环启动
  ▼
等待 LLOneBot 连接...
```

### 7.3 鉴权流程

```python
# server.py → _check_auth()
def _check_auth(self, websocket) -> bool:
    token = self.config.access_token
    headers = websocket.request_headers

    # 1. 从 Authorization 头提取 token
    auth = headers.get("authorization", "")
    # 支持 "Bearer xxx" 和裸 token 两种格式

    # 2. 比对
    if auth == f"Bearer {token}" or auth == token:
        return True

    # 3. 失败 → 关闭连接
    return False
```

### 7.4 CLI 参数

```bash
python main.py --config config.toml        # 指定配置文件
python main.py --host 0.0.0.0 --port 8080 # 覆盖地址端口
python main.py --token my-secret-token     # 覆盖 Token
python main.py --admin 123456              # 添加管理员（可多次）
python main.py --log-level DEBUG           # 覆盖日志级别
python main.py --no-hot-reload            # 禁用热重载
python main.py --version                  # 打印版本号
```

### 7.5 信号处理

```python
# 收到 Ctrl+C → 触发 handler.shutdown() → 优雅关闭
# 1. 停止接受新连接
# 2. 所有 Mixin 的 mixin_teardown() 依次执行
# 3. 所有 Extension 的 ext_unload() 依次执行
# 4. 关闭 WebSocket 连接
# 5. 取消所有后台任务
```

---

## 8. 处理器系统（Handler）

### 8.1 它是什么

`OneBotHandler` 是**事件分发的枢纽**。它不是一个固定类，而是通过 Mixin 多重继承**动态组装**出来的。

### 8.2 动态类组装

```python
# handler.py → create_handler_class()
def create_handler_class(mixin_classes):
    """
    把多个 Mixin 通过多重继承组合成一个 Handler 类。
    类似这样：
        class OneBotHandler(ConsoleMixin, BackupMixin, LogMixin, BaseHandler):
            pass
    """
    bases = tuple(mixin_classes) + (BaseHandler,)
    cls = type("OneBotHandler", bases, {})
    return cls
```

### 8.3 事件分发逻辑

收到一条事件后，Handler 按以下顺序处理：

```
原始 JSON
  ↓
BaseEvent.from_dict() → 构造具体事件对象
  ↓
handler.handle_event(event)
  ├── 1. 设置 self_id、client 引用
  ├── 2. 遍历所有 Mixin（按优先级排序），调用 mixin_on_event()
  ├── 3. 按事件类型分发：
  │     ├── MessageEvent → mixin_on_message()
  │     │     ├── GroupMessageEvent → mixin_on_group_message()
  │     │     └── PrivateMessageEvent → mixin_on_private_message()
  │     ├── NoticeEvent → mixin_on_notice()
  │     ├── RequestEvent → mixin_on_request()
  │     └── MetaEvent → mixin_on_meta()
  ├── 4. 遍历所有 Extension，调用同名钩子
  └── 5. 处理 Action 回包 → mixin_on_response()
```

### 8.4 Mixin 代理机制（_MixinProxy）

这是 Handler 最精巧的设计。当 Mixin 多重继承时，每个 Mixin 需要：
- 访问自己的属性和方法
- 同时能访问 Handler 的共享资源（config、client、logger）

```python
class _MixinProxy:
    """
    每个 Mixin 被包装成一个代理对象。
    - 自己的方法 → 直接调用
    - 自己的属性 → 直接读取
    - 不存在的属性 → fallback 到 Handler（共享资源）
    """
    def __getattr__(self, name):
        if name in self._own_methods:
            return self._own_methods[name]
        # fallback 到 handler
        return getattr(self._handler, name)
```

**效果**：在 Mixin 代码里写 `self.config` 能拿到配置，`self.client` 能拿到客户端，`self.logger` 能拿到日志——就像这些属性是定义在 Mixin 里的一样。

### 8.5 Handler 暴露给插件的属性

```python
handler.config           # Config 对象
handler.client           # OneBotClient（可能为 None）
handler.self_id          # 机器人 QQ 号
handler.whitelist        # WhitelistManager
handler.confirm_manager  # ConfirmManager
handler.extensions       # 已加载插件字典
handler.is_admin(qq)     # 检查管理员
handler.submit_sensitive_action(...)  # 提交敏感操作
```

---

## 9. Mixin 系统

### 9.1 它是什么

Mixin 是**内核级插件**，通过多重继承组合到 Handler 中，拥有完整权限。它们是项目功能的"积木"。

### 9.2 五大内置 Mixin

| Mixin | 文件 | 优先级 | 职责 |
|-------|------|:---:|------|
| **LogMixin** | `log_mixin.py` | 0（最高） | 记录所有事件和 Action 的结构化日志 |
| **StatsMixin** | `stats_mixin.py` | 3 | 统计消息类型/群/用户/小时维度 |
| **BackupMixin** | `backup_mixin.py` | 5 | 退群时自动备份白名单和群列表 |
| **ConsoleMixin** | `console_mixin.py` | 10 | 交互式终端（审批/发消息/管理插件） |
| **TaskMixin** | `task_mixin.py` | 20 | 定时任务调度（间隔/cron/一次性） |

### 9.3 Mixin 生命周期（完整）

```
Server 启动
  ↓
handler.mixin_setup_all()
  ├── LogMixin.mixin_setup(handler)       ← 最先执行
  ├── StatsMixin.mixin_setup(handler)
  ├── BackupMixin.mixin_setup(handler)
  ├── ConsoleMixin.mixin_setup(handler)
  └── TaskMixin.mixin_setup(handler)
  ↓
WebSocket 连接建立
  ↓
handler.mixin_on_connect_all(client)
  └── 每个 Mixin 的 mixin_on_connect(client)
  ↓
收到事件 → 每个 Mixin 的对应钩子
  ↓
收到 Action 回包 → 每个 Mixin 的 mixin_on_response()
  ↓
Server 关闭
  ↓
handler.mixin_teardown_all()
  └── 每个 Mixin 的 mixin_teardown()    ← 做清理、输出统计
```

### 9.4 Mixin 钩子一览

| 钩子 | 触发时机 | 典型用途 |
|------|---------|---------|
| `mixin_setup(handler)` | 启动初始化 | 创建目录、启动后台任务 |
| `mixin_on_connect(client)` | WS 连接建立 | 获取 client 引用 |
| `mixin_on_disconnect(client)` | WS 断开 | 清理连接相关状态 |
| `mixin_on_event(event)` | **每个事件** | 通用监听（日志/统计） |
| `mixin_on_message(event)` | 消息事件 | 消息处理 |
| `mixin_on_notice(event)` | 通知事件 | 群变动监听 |
| `mixin_on_request(event)` | 请求事件 | 加群/加好友处理 |
| `mixin_on_meta(event)` | 元事件 | 心跳/生命周期 |
| `mixin_on_response(response)` | Action 回包 | 结果处理 |
| `mixin_teardown()` | 关闭清理 | 保存数据、取消任务 |

### 9.5 优先级机制

```python
# 数字越小，越早执行
mixin_priority: int = 0    # LogMixin → 最先记录日志
mixin_priority: int = 5    # BackupMixin → 在业务逻辑前备份
mixin_priority: int = 10   # ConsoleMixin
mixin_priority: int = 20   # TaskMixin → 最后执行

# Handler 内部按优先级排序后依次调用
mixins.sort(key=lambda m: m.mixin_priority)
# → LogMixin → StatsMixin → BackupMixin → ConsoleMixin → TaskMixin
```

### 9.6 编写自定义 Mixin

```python
# onebot_server/mixin/keyword_alert_mixin.py
from .mixin_base import BaseMixin
from ..logger import get_logger

logger = get_logger()

class KeywordAlertMixin(BaseMixin):
    """监控消息中的敏感关键词"""

    mixin_name: str = "keyword_alert"
    mixin_priority: int = 8  # 在 Backup 之后、Console 之前

    def __init__(self, keywords=None, **kwargs):
        self.keywords = keywords or ["广告", "诈骗"]
        super().__init__(**kwargs)

    async def mixin_on_message(self, event):
        text = event.get_message_text()
        for kw in self.keywords:
            if kw in text:
                logger.warning(
                    f"[关键词告警] 群={event.group_id} "
                    f"用户={event.user_id} 触发={kw}"
                )
                break

    async def mixin_setup(self, handler):
        logger.info(f"[KeywordAlert] 监控关键词: {self.keywords}")
```

然后在 `config.toml` 的 `mixin.auto_load` 里加上 `"keyword_alert_mixin"` 即可。

---

## 10. Extension 系统

### 10.1 它是什么

Extension 是**用户级插件**，和 Mixin 的核心区别：

| 对比项 | Mixin | Extension |
|--------|-------|-----------|
| 继承位置 | 多重继承到 Handler | 独立实例，持有 Handler 引用 |
| 权限 | 完整（可访问一切） | 受限（只能通过 handler/client 交互） |
| 加载方式 | 启动时静态组合 | 运行时热加载/卸载 |
| 文件位置 | `onebot_server/mixin/` | `extensions/` |
| 能否碰 WS | ✅ 可以 | ❌ 不可以（只能通过 client） |
| 典型用途 | 基础设施（日志/备份/调度） | 业务逻辑（复读/自动回复/群管） |

### 10.2 Extension 生命周期

```
Server 启动 → ExtensionManager.cold_load_all()
  │
  ├── 扫描 extensions/*.py
  ├── importlib.import_module()
  ├── 找到 BaseExtension 子类
  ├── 实例化 → ext.ext_load(handler)
  ├── 存入 handler.extensions[name] = ext
  │
  ▼
WebSocket 连接 → ext.ext_on_connect(client)
  │
  ▼
事件到达 → ext.ext_on_message(event)
         → ext.ext_on_group_message(event)
         → ext.ext_on_private_message(event)
         → ext.ext_on_notice(event)
         → ...
  │
  ▼
Action 回包 → ext.ext_on_response(response)
  │
  ▼
文件变更（热重载） → ext.ext_unload() → 重新加载 → ext.ext_load(handler)
  │
  ▼
Server 关闭 → ext.ext_unload()
```

### 10.3 内置插件一览

| 插件 | 文件 | 功能 | 触发方式 |
|------|------|------|---------|
| Echo | `echo.py` | 复读机 | 群内发 `/echo 内容` |
| AutoReply | `autoreply.py` | 关键词自动回复 | 消息包含规则中的关键词 |
| Moderation | `moderation.py` | 群管（禁言/踢人/退群） | `/ban @某人`、`/kick @某人`、`/leave` |
| Welcome | `welcome.py` | 入群欢迎 | 自动监听 `group_increase` |

### 10.4 Extension 标准写法

```python
# extensions/my_plugin.py
from onebot_server import BaseExtension, build_message, SendGroupMsgAction

class MyPlugin(BaseExtension):
    name = "my_plugin"
    version = "1.0.0"
    description = "我的插件"
    priority = 100  # 数字小=先执行

    async def on_load(self):
        """加载时调用一次"""
        self.logger.info("[MyPlugin] 加载成功")

    async def on_group_message(self, event, client):
        """群消息钩子"""
        text = event.get_text().strip()
        if text == "/hello":
            await client.send(
                SendGroupMsgAction(
                    group_id=event.group_id,
                    message=build_message("Hello World!"),
                )
            )

    async def on_unload(self):
        """卸载时清理"""
        self.logger.info("[MyPlugin] 已卸载")
```

### 10.5 热重载机制

```
ExtensionManager 后台任务（每 2 秒）
  │
  ├── 扫描 extensions/ 目录
  ├── 对比文件修改时间（mtime）
  ├── 新增文件 → hot_load(name) → importlib 加载
  ├── 修改文件 → hot_unload → hot_load（重新加载）
  └── 删除文件 → hot_unload → 从 sys.modules 移除
```

> 热重载时，正在处理的消息可能使用旧版本插件。如果插件有后台任务，需要在 `on_unload()` 里正确取消。

### 10.6 Extension 可用的安全接口

```python
# 在 Extension 内部可直接使用
self.client              # OneBotClient（发消息/调 API）
self.handler             # OneBotHandler（访问更多资源）
self.handler.config      # 配置对象
self.handler.confirm_manager  # 提交敏感操作审批
self.handler.whitelist   # 白名单管理
self.is_admin(user_id)   # 检查管理员
self.get_config(key, default)  # 读配置
self.logger              # 日志
```

---

## 11. 确认管理系统（Confirm）

### 11.1 它是什么

敏感操作（禁言、踢人、退群等）不能直接执行，必须先**提交申请 → 管理员审批 → 通过后执行**。ConfirmManager 就是管理这个流程的系统。

### 11.2 核心流程

```
用户发 "/ban @某人"
  ↓
Moderation Extension 调用
  ↓
self.confirm_manager.submit(
    action_type="set_group_ban",
    params={"group_id": 123, "user_id": 456, "duration": 600},
    reason="禁言 10 分钟",
    operator_qq=event.user_id,
)
  ↓
返回 token（如 "a3f2b8c1d4e5f6a7"）
  ↓
消息通知管理员："有禁言申请待审批，Token: a3f2b8c1d4e5f6a7"
  ↓
管理员在控制台执行：
  approve a3f2b8c1d4e5f6a7
  ↓
ConfirmManager 标记 approved → 触发回调 → 执行 set_group_ban
  ↓
LLOneBot 执行禁言 → 返回结果
```

### 11.3 ConfirmRequest 数据结构

```python
@dataclass
class ConfirmRequest:
    token: str          # 唯一标识（16位hex）
    action_type: str    # "set_group_ban" / "set_group_kick" / "set_group_leave"
    params: dict        # 操作参数
    description: str    # 人类可读描述
    created_at: float   # 创建时间戳
    timeout: int        # 超时秒数
    approved: bool      # 是否已批准
    rejected: bool      # 是否被拒绝
    executor: int       # 提交者 QQ
    future: Future      # 用于等待审批结果
```

### 11.4 在控制台审批

```text
onebot > pending                    ← 查看待审批列表
[1] set_group_ban | 群=123 目标=456 | 禁言 10 分钟 | Token: a3f2b8...

onebot > approve a3f2b8c1d4e5f6a7  ← 批准
✅ 已批准并执行

onebot > reject a3f2b8c1d4e5f6a7   ← 拒绝
❌ 已拒绝
```

### 11.5 超时机制

```python
# ConfirmManager 后台清理任务
async def cleanup_task(self, interval=60):
    while True:
        await asyncio.sleep(interval)
        # 扫描所有请求，超时的自动标记为失败
        for token, req in self._requests.items():
            if req.is_expired() and not req.approved and not req.rejected:
                req.rejected = True
                req.future.set_result(False)
                logger.info(f"[Confirm] 请求 {token} 已超时自动拒绝")
```

### 11.6 在 Extension 中集成

```python
# 提交审批（不需要 await，立即返回 token）
token = self.confirm_manager.submit(
    action_type="set_group_kick",
    params={"group_id": event.group_id, "user_id": target_qq},
    reason=f"踢出 {target_qq}",
    operator_qq=event.user_id,
)
await client.send_text(event.group_id, f"⚠️ 已提交审批，Token: {token}")

# 如果需要等待审批结果（高级用法）
future = self.confirm_manager.submit_and_wait(...)  # 返回 Future
result = await future  # True=批准, False=拒绝/超时
```

---

## 12. 白名单系统（Whitelist）

### 12.1 它是什么

管理**哪些群和好友在受信任列表内**。用于退群确认、敏感操作授权等场景。数据持久化到 `data/` 目录的 JSON 文件。

### 12.2 存储结构

```
data/
├── group_whitelist.json    ← 受信任的群号列表
├── friend_whitelist.json   ← 受信任的好友 QQ 列表
└── group_list.json         ← 当前所在群的信息快照
```

### 12.3 白名单文件格式

```json
{
  "updated_at": "2026-08-17 14:30:00",
  "count": 3,
  "items": [123456, 234567, 345678]
}
```

### 12.4 API 一览

```python
whitelist = handler.whitelist

# ─── 群白名单 ───
whitelist.add_group(123456)           # 添加群
whitelist.remove_group(123456)        # 移除群
whitelist.is_group_whitelisted(123456) # 检查
whitelist.list_groups()               # 列出所有

# ─── 好友白名单 ───
whitelist.add_friend(789012)          # 添加好友
whitelist.remove_friend(789012)       # 移除
whitelist.is_friend_whitelisted(789012)

# ─── 群列表缓存 ───
whitelist.update_group_list([...])    # 更新群列表快照
whitelist.get_group_info(group_id)    # 查单个群信息
whitelist.remove_group_from_list(gid) # 退群时移除

# ─── 批量操作 ───
whitelist.import_groups([111, 222, 333])  # 批量导入
whitelist.export_all()                    # 导出全部数据
```

### 12.5 和 BackupMixin 的协作

```
退群事件发生
  ↓
BackupMixin 检测到 user_id == self_id（机器人自己退群）
  ↓
自动调用 whitelist.remove_group_from_list(group_id)
  ↓
同时触发全量备份 → backups/backup_20260817_143000/
  ├── group_whitelist.json
  ├── friend_whitelist.json
  └── group_list.json
```

---

## 13. 系统协作全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                      LLOneBot / NapCat                         │
│                  (QQ 协议端，运行在手机/PC)                      │
└──────────────────────┬──────────────────────────────────────────┘
                       │ WebSocket (反向连接)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OneBotServer                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Config (TOML)                          │  │
│  │        端口/Token/日志/管理员/超时/路径...                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Logger (Loguru)                             │  │
│  │         控制台彩色 + 文件轮转 + 按天分片                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │          OneBotHandler (动态组装)                         │  │
│  │  ┌─────────────────────────────────────────────────────┐   │  │
│  │  │  ConsoleMixin (priority=10)                        │   │  │
│  │  │  BackupMixin  (priority=5)                         │   │  │
│  │  │  StatsMixin   (priority=3)                         │   │  │
│  │  │  LogMixin     (priority=0) ← 最先执行              │   │  │
│  │  │  TaskMixin    (priority=20) ← 最后执行             │   │  │
│  │  └─────────────────────────────────────────────────────┘   │  │
│  │  ┌─────────────────────────────────────────────────────┐   │  │
│  │  │  ExtensionManager (热加载/卸载/重载)                │   │  │
│  │  │  ├── echo.py                                       │   │  │
│  │  │  ├── autoreply.py                                  │   │  │
│  │  │  ├── moderation.py                                 │   │  │
│  │  │  └── welcome.py                                    │   │  │
│  │  └─────────────────────────────────────────────────────┘   │  │
│  │  ┌─────────────────────────────────────────────────────┐   │  │
│  │  │  ConfirmManager (敏感操作审批)                      │   │  │
│  │  │  WhitelistManager (白名单持久化)                    │   │  │
│  │  └─────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              OneBotClient (WS 连接封装)                    │  │
│  │  send() / call() / echo配对 / 写锁 / 快捷方法             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 14. 数据流向：一条消息的旅程

以"群内用户发 `/echo 你好`"为例，完整追踪数据流动：

```
① QQ 用户发消息 "echo 你好"
       │
       ▼
② LLOneBot 收到 QQ 消息，序列化为 OneBot 11 JSON
   {
     "post_type": "message",
     "message_type": "group",
     "group_id": 123456,
     "user_id": 789012,
     "message": [{"type": "text", "data": {"text": "/echo 你好"}}],
     ...
   }
       │
       ▼ (WebSocket → ws://127.0.0.1:8765)
③ Server._accept_connection() 接收
   → 鉴权检查（Token 比对）
   → 创建 OneBotClient(websocket)
   → handler.mixin_on_connect(client)
       │
       ▼
④ handler.handle_event(raw_dict)
   → BaseEvent.from_dict() → GroupMessageEvent 对象
   → 设置 self_id、client 引用
       │
       ▼
⑤ 按优先级遍历 Mixin：
   → LogMixin.mixin_on_message(event)      📝 记录日志
   → StatsMixin.mixin_on_message(event)    📊 统计计数
   → BackupMixin.mixin_on_message(event)   (不处理消息事件，跳过)
   → ConsoleMixin.mixin_on_message(event) (不处理消息事件，跳过)
   → TaskMixin.mixin_on_message(event)     (不处理消息事件，跳过)
       │
       ▼
⑥ 按优先级遍历 Extension：
   → EchoExtension.on_group_message(event, client)
     → 检测文本以 "/echo " 开头 ✓
     → content = "你好"
     → client.send(SendGroupMsgAction(group_id=123456, message=["你好"]))
       │
       ▼
⑦ Client.send() 内部：
   → 生成 echo = "uuid-abc-123"
   → JSON 序列化 → '{"action":"send_group_msg","params":{...},"echo":"uuid-abc-123"}'
   → async with write_lock: await ws.send(payload)
       │
       ▼ (WebSocket → LLOneBot)
⑧ LLOneBot 收到 Action，调用 QQ API 发送消息
   → QQ 群里出现 "你好"
   → LLOneBot 返回结果 JSON
       │
       ▼ (WebSocket → Server)
⑨ Client 收到回包：
   → echo = "uuid-abc-123"
   → 找到 pending["uuid-abc-123"] 的 Future
   → future.set_result(ActionResponse(status="ok", retcode=0, ...))
       │
       ▼
⑩ handler.mixin_on_response(response)
   → LogMixin 记录 "Action OK echo=uuid-abc-123"
   → 流程结束 ✅
```

---

## 附录：文件职责速查表

| 文件 | 系统 | 职责 |
|------|------|------|
| `config.py` | 配置 | TOML 加载、单例、路径查询 |
| `logger.py` | 日志 | Loguru 初始化、控制台+文件双输出 |
| `events.py` | 事件 | 12 种事件 dataclass + 自动分发 |
| `actions.py` | 动作 | 20+ Action 类 + 序列化 + 快捷构造 |
| `segments.py` | 消息段 | 文本/图片/@/表情/回复构造工具 |
| `client.py` | 客户端 | WS 封装、echo 配对、写锁、快捷方法 |
| `server.py` | 服务器 | 组装一切、启动 WS、CLI、鉴权 |
| `handler.py` | 处理器 | 动态类组装、事件分发、Mixin 代理 |
| `mixin_base.py` | Mixin | BaseMixin 基类、生命周期定义 |
| `mixin/log_mixin.py` | Mixin | 结构化日志记录 |
| `mixin/stats_mixin.py` | Mixin | 消息统计 + 可继承扩展 |
| `mixin/backup_mixin.py` | Mixin | 退群自动备份 |
| `mixin/console_mixin.py` | Mixin | 交互式终端 + 审批 |
| `mixin/task_mixin.py` | Mixin | 定时任务调度 |
| `extension_base.py` | Extension | BaseExtension 基类 |
| `extension_manager.py` | Extension | 热加载/卸载/重载/文件监控 |
| `confirm.py` | 确认 | 敏感操作审批流程 |
| `whitelist.py` | 白名单 | 群/好友白名单持久化 |

---

> 📌 **阅读建议**：如果你是新接手这个项目，推荐按以下顺序阅读源码：
> 1. `config.py` → 理解配置怎么读
> 2. `events.py` → 理解数据怎么进来
> 3. `actions.py` + `segments.py` → 理解数据怎么出去
> 4. `client.py` → 理解 WS 通信
> 5. `handler.py` → 理解事件分发枢纽
> 6. `mixin_base.py` → 理解 Mixin 机制
> 7. `extension_base.py` + `extension_manager.py` → 理解插件系统
> 8. 最后看 `server.py` → 把所有东西串起来
