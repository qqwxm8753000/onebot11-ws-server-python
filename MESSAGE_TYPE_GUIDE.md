# 如何确定聊天事件是群消息还是私聊

> 适用版本：OneBot 11 Server v2.1
> 对应文件：`onebot_server/events.py`、`onebot_server/handler.py`、`onebot_server/extension_base.py`

---

## 一、核心结论（先看这个）

在你的项目里，**有三种方式**可以判断一条消息是群聊还是私聊，从推荐到不推荐排列：

| 方式 | 怎么做 | 推荐度 | 说明 |
|------|--------|--------|------|
| **① 用不同的钩子函数** | 群消息重写 `ext_on_group_message`，私聊重写 `ext_on_private_message` | ⭐⭐⭐⭐⭐ | **最推荐**，handler 已经帮你分好了 |
| **② 用 `isinstance` 判断事件类型** | `isinstance(event, GroupMessageEvent)` | ⭐⭐⭐⭐ | 在通用钩子里做分支判断 |
| **③ 读 `event.message_type` 字段** | `event.message_type == "group"` | ⭐⭐⭐ | 直接读原始字段，最底层 |

---

## 二、方式一：用不同的钩子（最推荐）

### 原理

`handler.py` 的 `_dispatch_message()` 做了**三级分发**：

```
原始事件 dict
   │
   ▼
BaseEvent.from_dict()  →  根据 message_type 自动构造：
   │                         "group"   → GroupMessageEvent
   │                         "private" → PrivateMessageEvent
   │
   ▼
_dispatch_message(event)
   │
   ├── 第1级：所有消息 → ext_on_message()         ← 通用入口
   │
   ├── 第2级：isinstance(event, GroupMessageEvent)
   │           → ext_on_group_message()            ← 仅群消息
   │
   └── 第3级：isinstance(event, PrivateMessageEvent)
               → ext_on_private_message()         ← 仅私聊
```

**你只需要重写对应的钩子，handler 会自动把消息路由到正确的函数。**

### 代码示例

```python
# extensions/my_plugin.py
from onebot_server.extension_base import BaseExtension
from onebot_server.events import GroupMessageEvent, PrivateMessageEvent

class MyPlugin(BaseExtension):
    ext_name = "my_plugin"
    description = "演示群消息和私聊的区分"

    # ✅ 方式一（推荐）：用不同钩子，自动分流
    async def ext_on_group_message(self, event: GroupMessageEvent):
        """这个方法只会在群消息时触发"""
        group_id = event.group_id
        user_id = event.user_id
        text = event.get_message_text()
        print(f"[群 {group_id}] {user_id} 说：{text}")

    async def ext_on_private_message(self, event: PrivateMessageEvent):
        """这个方法只会在私聊时触发"""
        user_id = event.user_id
        text = event.get_message_text()
        print(f"[私聊] {user_id} 说：{text}")
```

**就这么简单。** 你不需要写任何 `if/else` 判断，handler 已经帮你分好了。

---

## 三、方式二：在通用钩子里用 `isinstance` 判断

如果你只想写一个 `ext_on_message` 钩子，在里面同时处理群消息和私聊，可以用 `isinstance` 判断：

```python
from onebot_server.extension_base import BaseExtension
from onebot_server.events import (
    MessageEvent, GroupMessageEvent, PrivateMessageEvent
)

class MyPlugin(BaseExtension):
    ext_name = "my_plugin"

    async def ext_on_message(self, event: MessageEvent):
        """所有消息都会进这里（群 + 私聊）"""

        if isinstance(event, GroupMessageEvent):
            # 群消息逻辑
            await self._handle_group(event)
        elif isinstance(event, PrivateMessageEvent):
            # 私聊逻辑
            await self._handle_private(event)
        else:
            # 兜底（理论上不会走到这里）
            print(f"未知消息类型: {event.message_type}")

    async def _handle_group(self, event: GroupMessageEvent):
        group_id = event.group_id
        sender_card = event.sender.card      # 群名片
        sender_role = event.sender.role     # owner/admin/member
        anonymous = event.anonymous         # 是否匿名（None 表示非匿名）
        # ...

    async def _handle_private(self, event: PrivateMessageEvent):
        target_id = event.target_id        # 对端 QQ 号
        # ...
```

### 事件类型继承关系

```
BaseEvent
  └── MessageEvent（消息事件基类）
        ├── GroupMessageEvent    ← message_type == "group"
        └── PrivateMessageEvent  ← message_type == "private"
```

`isinstance(event, MessageEvent)` → 所有消息（群+私聊）
`isinstance(event, GroupMessageEvent)` → 仅群消息
`isinstance(event, PrivateMessageEvent)` → 仅私聊

---

## 四、方式三：直接读 `message_type` 字段

最底层的方式，直接读 OneBot 11 协议原始字段：

```python
async def ext_on_message(self, event):
    msg_type = event.message_type

    if msg_type == "group":
        # 群消息
        group_id = event.group_id
        print(f"群消息，群号={group_id}")
    elif msg_type == "private":
        # 私聊
        print("私聊消息")
    else:
        print(f"未知 message_type: {msg_type}")
```

**什么时候用这种方式？** 几乎不用。除非你在写一个极其通用的中间件，需要兼容未来可能新增的消息类型（比如"讨论组"之类）。日常开发用方式一或方式二就够了。

---

## 五、群消息和私聊各自的"专属字段"

两种事件的字段有差异，写插件时要注意：

### 群消息 `GroupMessageEvent` 独有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `group_id` | `int` | 群号 |
| `anonymous` | `Optional[Anonymous]` | 匿名信息，非匿名时为 `None` |
| `sender.card` | `str` | 群名片（非群主/管理员可能为空） |
| `sender.role` | `str` | `owner` / `admin` / `member` |
| `sender.title` | `str` | 群头衔 |

### 私聊 `PrivateMessageEvent` 独有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_id` | `int` | 对端 QQ 号（发消息给你的那个人） |
| `sub_type` | `str` | `friend` / `group` / `other`（群临时会话/陌生人） |

### 两者共有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `message_type` | `str` | `"group"` 或 `"private"` |
| `message_id` | `int` | 消息 ID |
| `user_id` | `int` | 发送者 QQ 号 |
| `message` | `List[MessageSegment]` | 消息段列表 |
| `raw_message` | `str` | 原始消息文本 |
| `sender.user_id` | `int` | 发送者 QQ |
| `sender.nickname` | `str` | 昵称 |
| `time` | `int` | 时间戳 |
| `self_id` | `int` | 机器人自身 QQ |

---

## 六、实战示例：一个插件同时处理群和私聊

```python
# extensions/echo_plus.py
from onebot_server.extension_base import BaseExtension
from onebot_server.events import (
    MessageEvent, GroupMessageEvent, PrivateMessageEvent
)
from onebot_server.segments import text

class EchoPlus(BaseExtension):
    """
    增强版复读机：
    - 群里说 "复读 xxx" → 复读 xxx 并 @ 发送者
    - 私聊说 "复读 xxx" → 直接复读 xxx
    """
    ext_name = "echo_plus"
    description = "区分群/私聊的智能复读"

    async def ext_on_message(self, event: MessageEvent):
        text = event.get_message_text().strip()

        if not text.startswith("复读"):
            return

        content = text[2:].strip()
        if not content:
            return

        if isinstance(event, GroupMessageEvent):
            # 群里：回复并 @ 发送者
            reply = [
                text(f"[群复读] "),
                text(f"@发送者 "),   # 实际应构造 at 段
                text(content),
            ]
            await self.send_group_msg(event.group_id, reply)

        elif isinstance(event, PrivateMessageEvent):
            # 私聊：直接回复
            await self.send_private_msg(event.user_id, [text(f"[私聊复读] {content}")])
```

---

## 七、Mixin 里怎么区分？

如果你在写 **Mixin**（不是 Extension），钩子名是 `mixin_on_message`，逻辑完全一样：

```python
# onebot_server/mixin/my_mixin.py
from onebot_server.mixin_base import BaseMixin
from onebot_server.events import GroupMessageEvent, PrivateMessageEvent

class MyMixin(BaseMixin):
    mixin_name = "my_mixin"
    mixin_priority = 50

    async def mixin_on_message(self, event):
        if isinstance(event, GroupMessageEvent):
            print(f"[Mixin] 群消息: 群={event.group_id}")
        elif isinstance(event, PrivateMessageEvent):
            print(f"[Mixin] 私聊: 用户={event.user_id}")
```

Mixin 的钩子执行顺序在 Extension **之前**（因为 Mixin 是内核级，优先级更高），所以你也可以在 Mixin 里做统一的消息预处理/过滤，再交给 Extension 处理。

---

## 八、常见坑

### ❌ 坑1：在 `ext_on_message` 里直接访问 `event.group_id`

```python
async def ext_on_message(self, event):
    group_id = event.group_id  # 💥 私聊消息没有这个字段！
```

**正确做法**：先判断类型，或者用 `getattr(event, "group_id", 0)` 做兜底。

### ❌ 坑2：以为 `event.user_id` 在群里是群号

`user_id` 永远是**发送者 QQ**，不是群号。群号在 `event.group_id`。

### ❌ 坑3：忘记 `sub_type` 区分私聊来源

私聊的 `sub_type` 有三种：`friend`（好友）、`group`（群临时会话）、`other`（陌生人）。如果你只处理好友私聊：

```python
async def ext_on_private_message(self, event: PrivateMessageEvent):
    if event.sub_type == "friend":
        # 仅处理好友私聊
        ...
```

### ❌ 坑4：匿名消息的 `user_id` 是 0

群里匿名发言时，`event.user_id == 0`，`event.sender.nickname` 是匿名名（如"匿名者123"），`event.anonymous` 不为 `None`。

---

## 九、速查表

| 我想做什么 | 写哪个钩子 | 事件类型 |
|-----------|-----------|---------|
| 处理所有消息 | `ext_on_message` | `MessageEvent` |
| 只处理群消息 | `ext_on_group_message` | `GroupMessageEvent` |
| 只处理私聊 | `ext_on_private_message` | `PrivateMessageEvent` |
| 在通用钩子里分支 | `isinstance(event, GroupMessageEvent)` | — |
| 读原始字段判断 | `event.message_type == "group"` | — |

---

> **一句话总结**：**写两个钩子 `ext_on_group_message` + `ext_on_private_message`，让 handler 帮你分流，是最干净、最不容易出错的方式。** 只有当你需要统一的预处理逻辑时，才在 `ext_on_message` 里用 `isinstance` 做分支。
