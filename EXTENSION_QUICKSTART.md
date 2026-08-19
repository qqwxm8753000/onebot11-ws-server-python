# Extension 开发快速指南

## 5 分钟写一个插件

### Step 1：复制模板
```bash
cp extensions/_template.py onebot_server/extensions/my_bot.py
```

### Step 2：改类名 + name
```python
class MyBot(BaseExtension, LogMixin):
    name: str = "my_bot"
    description: str = "我的第一个插件"
    priority: int = 100
```

### Step 3：写业务逻辑
```python
async def on_group_message(self, event, client):
    text = event.get_text().strip()
    if text == "/hello":
        await self.safe_send_group_msg(
            group_id=event.group_id,
            message=build_message("你好！"),
        )
```

### Step 4：热加载
```
# 控制台输入
load my_bot
```

---

## 你能用什么（Mixin 能力表）

| Mixin | 提供的方法 | 说明 |
|-------|-----------|------|
| `LogMixin` | `safe_send_group_msg` / `safe_send_private_msg` / `safe_send_msg` / `call_action` / `submit_confirm` / `logger` | **最常用，发消息 + 审批全靠它** |
| `StatsMixin` | `get_stats()` / `get_group_stats(group_id)` | 消息计数、频率统计 |
| `BackupMixin` | `backup_now()` / `get_backup_list()` | 手动触发备份 |
| `ConsoleMixin` | `register_command(name, handler)` | 注册 CLI 子命令 |
| `TaskMixin` | `schedule_task(name, interval, coro)` / `cancel_task(name)` | 定时任务 |

---

## 你不能做什么（安全边界）

| ❌ 禁止 | ✅ 替代方案 |
|---------|------------|
| 直接 `import handler` / `import server` | 用 `self.safe_send_*` |
| 直接操作 WebSocket 连接 | 通过 `client` 参数 + `call_action()` |
| 绕过 ConfirmManager 发敏感操作 | 用 `self.submit_confirm()` |
| 修改 `config.toml` | 用插件私有 JSON 配置文件 |
| 访问其他 Extension 的内部状态 | 不允许（隔离设计） |

---

## 完整命令速查

```
# 插件管理
load <name>        # 热加载
unload <name>      # 热卸载
reload <name>      # 热重载（先卸后装）
ext list           # 查看已加载插件
ext info <name>    # 查看插件详情

# 审批管理
confirm list       # 查看待审批
approve <token>    # 批准
reject <token>     # 拒绝

# 系统
status             # 全局状态
help               # 帮助
quit               # 优雅退出
```

---

## 架构图

详见 `ARCHITECTURE.md`，包含：
- 总览架构图（Mermaid）
- 权限边界图（内核 / Mixin / Extension 三层）
- 事件流时序图
- 生命周期状态图
- 目录结构图
