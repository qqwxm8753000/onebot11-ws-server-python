"""
autoreply.py — 关键词自动回复插件
==========================================
功能：匹配关键词自动回复，规则从 JSON 文件加载。
演示 Extension 读取配置文件 + 消息处理。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

from onebot_server import (
    BaseExtension,
    GroupMessageEvent,
    build_message,
    text_segment,
)


class AutoReplyExtension(BaseExtension):
    """关键词自动回复。"""

    ext_name: str = "autoreply"
    description: str = "关键词自动回复"
    priority: int = 20
    version: str = "1.0.0"

    def __init__(self):
        super().__init__()
        self._rules: Dict[str, str] = {}
        self._config_file: str = ""

    async def ext_load(self, handler: Any) -> bool:
        """加载时读取配置文件。"""
        # 调用父类加载
        result = await super().ext_load(handler)

        # 确定配置文件路径
        ext_dir = getattr(handler, "config", None)
        data_dir = "data"
        if ext_dir:
            data_dir = "data"
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        self._config_file = os.path.join(data_dir, "autoreply.json")
        self._load_rules()

        # 如果配置文件不存在，写入默认规则
        if not self._rules:
            self._rules = {
                "在吗": "在的，有什么可以帮你？",
                "你好": "你好呀！我是机器人～",
                "帮助": "发送 /help 查看命令列表",
                "晚安": "晚安，好梦 🌙",
                "谢谢": "不客气！",
            }
            self._save_rules()

        return result

    async def ext_on_group_message(self, event: GroupMessageEvent) -> None:
        """匹配关键词并回复。"""
        text = event.get_message_text().strip()

        # 忽略以 / 开头的命令
        if text.startswith("/"):
            return

        for keyword, reply in self._rules.items():
            if keyword in text:
                message = build_message(text_segment(reply))
                await self.safe_send_group_msg(
                    group_id=event.group_id,
                    message=message,
                )
                break  # 只匹配第一个

    def _load_rules(self) -> None:
        """从 JSON 加载规则。"""
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, "r", encoding="utf-8") as f:
                    self._rules = json.load(f)
        except Exception:
            self._rules = {}

    def _save_rules(self) -> None:
        """保存规则到 JSON。"""
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._rules, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
