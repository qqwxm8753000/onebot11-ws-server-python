# OneBot 11 Server 架构图

## 总览架构

```mermaid
flowchart TB
    subgraph LLOneBot["LLOneBot (QQ 客户端侧)"]
        QQ[("QQ 账号<br/>登录会话")]
        LLOB["LLOneBot 插件<br/>OneBot 协议转换"]
        QQ <--> LLOB
    end

    subgraph Network["网络通信层"]
        WS["WebSocket 反向连接<br/>ws://127.0.0.1:8765<br/>Bearer Token 鉴权"]
    end

    subgraph Core["微内核 (onebot_server/)"]
        direction TB
        subgraph Kernel["不可变核心"]
            Server["WebSocketServer<br/>监听 / 鉴权 / 连接管理"]
            Handler["OneBotHandler<br/>事件枢纽 + MRO 分发"]
            Client["OneBotClient<br/>send / call / echo 配对"]
            Config["ConfigManager<br/>TOML 热重载"]
            Logger["Logger<br/>Loguru 封装"]
        end

        subgraph MixinLayer["Mixin 能力层 (可插拔)"]
            direction LR
            LogM["LogMixin<br/>监听所有事件<br/>写入日志"]
            BackupM["BackupMixin<br/>退群自动备份<br/>白名单持久化"]
            ConsoleM["ConsoleMixin<br/>CLI 命令<br/>审批/管理"]
            TaskM["TaskMixin<br/>定时任务<br/>周期执行"]
            StatsM["StatsMixin<br/>消息统计<br/>频率计数"]
            CustomM["CustomMixin<br/>用户自定义<br/>可继承其他Mixin"]
        end

        subgraph ExtensionLayer["Extension 业务层 (热加载)"]
            direction LR
            Echo["echo.py<br/>复读机"]
            AutoReply["autoreply.py<br/>关键词回复"]
            Moderation["moderation.py<br/>群管(需审批)"]
            Welcome["welcome.py<br/>入群欢迎"]
            UserExt["your_ext.py<br/>用户插件"]
        end

        subgraph Safety["安全子系统"]
            Confirm["ConfirmManager<br/>敏感操作审批<br/>Token 5min 过期"]
            Whitelist["WhitelistManager<br/>群/好友白名单<br/>JSON 持久化"]
        end
    end

    subgraph Storage["持久化层"]
        Cfg["config.toml<br/>端口/Token/IP/开关"]
        WL["*.json<br/>白名单/群列表/备份"]
        Logs["logs/*.log<br/>按大小轮转"]
    end

    %% 连接关系
    LLOB == "反向 WS" ==> WS
    WS --> Server
    Server --> Handler
    Handler <--> Client

    %% Mixin 注入到 Handler
    LogM -. "MRO 多重继承" .-> Handler
    BackupM -. "MRO 多重继承" .-> Handler
    ConsoleM -. "MRO 多重继承" .-> Handler
    TaskM -. "MRO 多重继承" .-> Handler
    StatsM -. "MRO 多重继承" .-> Handler
    CustomM -. "MRO 多重继承" .-> Handler

    %% Extension 继承 Mixin（只能间接调用）
    Echo -->|"继承"| LogM
    AutoReply -->|"继承"| StatsM
    Moderation -->|"继承"| ConsoleM
    Welcome -->|"继承"| BackupM
    UserExt -->|"继承"| CustomM

    %% Extension 只能走安全通道
    ExtensionLayer -->|"safe_send_*<br/>间接调用"| Client
    ExtensionLayer -->|"提交审批"| Confirm
    ExtensionLayer -->|"查询白名单"| Whitelist

    %% 配置/日志/存储
    Config <--> Cfg
    Logger --> Logs
    Whitelist <--> WL
    BackupM --> WL
```

## 权限边界图

```mermaid
flowchart LR
    subgraph L1["🔴 内核层 (不可修改)"]
        A1["WebSocketServer"]
        A2["OneBotHandler"]
        A3["OneBotClient"]
        A4["ConfirmManager"]
        A5["WhitelistManager"]
    end

    subgraph L2["🟡 Mixin 层 (可插拔/可继承)"]
        B1["LogMixin"]
        B2["BackupMixin"]
        B3["ConsoleMixin"]
        B4["TaskMixin"]
        B5["StatsMixin"]
        B6["CustomMixin"]
    end

    subgraph L3["🟢 Extension 层 (热加载/热卸载)"]
        C1["echo.py"]
        C2["autoreply.py"]
        C3["moderation.py"]
        C4["welcome.py"]
        C5["your_ext.py"]
    end

    L3 -->|"继承(extends)"| L2
    L3 -.->|"❌ 禁止直接访问"| L1
    L2 -->|"MRO 注入"| L1
```

## 事件流时序图

```mermaid
sequenceDiagram
    participant QQ as QQ 用户
    participant LLOB as LLOneBot
    participant WS as WebSocketServer
    participant H as OneBotHandler
    participant M as Mixin(Log/Stats/...)
    participant E as Extension(echo/moderation)
    participant C as ConfirmManager

    QQ->>LLOB: 发送群消息 "@机器人 你好"
    LLOB->>WS: JSON 事件 (WebSocket 帧)
    WS->>H: 原始事件 dict
    H->>H: BaseEvent.from_dict() 自动分发
    H->>M: mixin_on_group_message(event)
    Note over M: LogMixin 写日志<br/>StatsMixin 计数

    alt 消息匹配 Extension 规则
        H->>E: on_group_message(event, client)
        E->>E: 业务逻辑判断
        E->>C: 是否需要审批?
        alt 敏感操作(禁言/踢人/退群)
            E->>C: submit_confirm(action, params)
            C-->>E: confirm_token
            E->>LLOB: 回复 "已提交审批, 等待管理员确认"
        else 普通回复
            E->>LLOB: safe_send_group_msg(text)
            LLOB->>QQ: 机器人回复消息
        end
    end

    Note over C: 管理员发送 /approve <token>
    C->>LLOB: 执行原 action (ban/kick/leave)
    LLOB->>QQ: 操作生效
```

## 生命周期图

```mermaid
stateDiagram-v2
    [*] --> 启动: python main.py
    启动 --> 加载TOML: config.toml 解析
    加载TOML --> 初始化内核: Server / Handler / Client
    初始化内核 --> 冷加载Mixin: MRO 组合到 Handler
    冷加载Mixin --> 冷加载Extension: 扫描 extensions/ 目录
    冷加载Extension --> 监听WS: 等待 LLOneBot 连接
    监听WS --> 运行中: LLOneBot 连入

    state 运行中 {
        [*] --> 事件循环
        事件循环 --> Mixin分发
        Mixin分发 --> Extension响应
        Extension响应 --> 安全校验
        安全校验 --> 发送Action
    }

    运行中 --> 热加载: CLI: load xxx
    运行中 --> 热卸载: CLI: unload xxx
    运行中 --> 热重载: CLI: reload xxx
    热加载 --> 运行中
    热卸载 --> 运行中
    热重载 --> 运行中

    运行中 --> 退群事件: group_decrease
    退群事件 --> 自动备份: BackupMixin 触发
    自动备份 --> 运行中

    运行中 --> 收到退出信号: Ctrl+C / SIGTERM
    收到退出信号 --> 冷卸载Extension: 逆序卸载所有插件
    冷卸载Extension --> 冷卸载Mixin: 逆序清理资源
    冷卸载Mixin --> 保存配置: 白名单/群列表写盘
    保存配置 --> [*]: 进程退出
```

## 目录结构图

```mermaid
flowchart TB
    Root["onebot11_server/"]
    Root --> Main["main.py<br/>━━━━━━━━━━<br/>入口: 读 TOML → 创建 Server → run_forever()"]
    Root --> Cfg["config.toml<br/>━━━━━━━━━━<br/>port / host / token<br/>admins / whitelist<br/>mixin / extension 开关"]
    Root --> Req["requirements.txt<br/>━━━━━━━━━━<br/>websockets<br/>loguru"]
    Root --> Doc["DOCUMENTATION.md<br/>━━━━━━━━━━<br/>1700+ 行完整文档"]

    Root --> Pkg["onebot_server/<br/>━━━━━━━━━━<br/>核心包"]
    Pkg --> Init["__init__.py<br/>统一导出"]
    Pkg --> Config["config.py<br/>TOML 管理 + 热重载"]
    Pkg --> Logger["logger.py<br/>Loguru 封装"]
    Pkg --> Events["events.py<br/>12 种事件模型"]
    Pkg --> Actions["actions.py<br/>20+ Action + 消息段"]
    Pkg --> Client["client.py<br/>WS 客户端封装"]
    Pkg --> Confirm["confirm.py<br/>审批管理器"]
    Pkg --> Whitelist["whitelist.py<br/>白名单管理"]
    Pkg --> ExtBase["extension_base.py<br/>Extension 基类"]
    Pkg --> ExtMgr["extension_manager.py<br/>4 种加载模式"]
    Pkg --> Handler["handler.py<br/>事件枢纽 + Mixin 代理"]
    Pkg --> Server["server.py<br/>WS 服务器 + CLI"]

    Pkg --> Mixin["mixin/<br/>━━━━━━━━━━<br/>内置 Mixin"]
    Mixin --> LogMix["log_mixin.py")
    Mixin --> BackupMix["backup_mixin.py")
    Mixin --> ConsoleMix["console_mixin.py")
    Mixin --> TaskMix["task_mixin.py")
    Mixin --> StatsMix["stats_mixin.py<br/>(继承 StatsMixin)")

    Root --> Exts["extensions/<br/>━━━━━━━━━━<br/>用户插件"]
    Exts --> Echo["echo.py")
    Exts --> AutoReply["autoreply.py")
    Exts --> Moderation["moderation.py")
    Exts --> Welcome["welcome.py")

    Root --> Tests["tests/<br/>━━━━━━━━━━<br/>55 项测试"]
```
