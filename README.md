# OneBot 11 Server v2.1

一个用 Python 编写的 **OneBot 11 协议 WebSocket 服务器**，专为对接 LLOneBot / NapCat 设计。

## 架构亮点

- **微内核 + Mixin 组合**：WS 核心不可变，功能全部插件化
- **双层插件系统**：Mixin（内核级） + Extension（用户级），权限隔离
- **热加载 / 冷加载**：运行时增删插件无需重启
- **敏感操作确认**：ban/kick/leave 必须审批，防止误操作
- **退群自动备份**：白名单和群列表自动存档
- **Loguru 日志**：按大小轮转，按天数保留
- **TOML 配置**：清晰可读，支持命令行覆盖

## 快速开始

```bash
# 1. 安装依赖
pip install websockets loguru

# 2. 启动
python main.py

# 3. LLOneBot / NapCat 填 ws://127.0.0.1:8765 + Token
```

## 项目结构

```
onebot11_server/
├── main.py                     # 主入口
├── config.toml                 # TOML 主配置
├── requirements.txt
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md            # 架构图（5 张 Mermaid 图）
├── DOCUMENTATION.md           # 完整文档（1700+ 行）
├── EXTENSION_QUICKSTART.md    # 插件开发快速入门
├── onebot_server/             # 核心包
│   ├── config.py             # TOML 配置管理
│   ├── logger.py             # Loguru 封装
│   ├── client.py             # WebSocket 客户端封装
│   ├── events.py             # 12 种事件模型
│   ├── actions.py            # 20+ Action API
│   ├── segments.py           # 消息段构造
│   ├── confirm.py            # 敏感操作确认
│   ├── whitelist.py         # 白名单管理
│   ├── extension_base.py    # Extension 基类
│   ├── extension.py          # Extension 实现
│   ├── extension_manager.py  # 插件管理器
│   ├── handler.py            # 事件枢纽 + Mixin 代理
│   ├── server.py             # WebSocket 服务器 + CLI
│   └── mixin/               # 内置 Mixin
│       ├── log_mixin.py
│       ├── backup_mixin.py
│       ├── console_mixin.py
│       ├── task_mixin.py
│       └── stats_mixin.py
├── extensions/                # 用户插件
│   ├── _template.py          # 插件模板（带详细注释）
│   ├── echo.py              # 复读机
│   ├── autoreply.py         # 关键词回复
│   ├── autoreply.json       # 回复规则
│   ├── moderation.py        # 群管（需审批）
│   └── welcome.py           # 入群欢迎
└── tests/
    └── test_all.py           # 55 项测试
```

## 测试结果

```
55 passed, 2 warnings in 2.36s
```

## 文档

- `ARCHITECTURE.md` — 5 张架构图（总览/权限/时序/生命周期/目录）
- `DOCUMENTATION.md` — 完整技术文档（20 章，1700+ 行）
- `EXTENSION_QUICKSTART.md` — 5 分钟写第一个插件

## 对接 NapCat / LLOneBot 配置

```json
{
  "url": "ws://127.0.0.1:8765",
  "messagePostFormat": "array",
  "reportSelfMessage": false,
  "token": "和 config.toml 里一致",
  "reconnectInterval": 5000,
  "heartInterval": 30000
}
```

## License

MIT
