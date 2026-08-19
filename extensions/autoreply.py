"""
autoreply.py — 关键词自动回复
==============================
从 autoreply.json 读取规则:
[
  {"keyword": "在吗", "reply": "在的在的，有事直说~"},
  {"keyword": "你好", "reply": "你好呀！"}
]
"""

import json
import os
from ..extension_base import BaseExtension
from ..actions import SendGroupMsgAction, SendPrivateMsgAction
from ..segments import build_message


class AutoReplyExtension(BaseExtension):
    """关键词自动回复"""

    name = "autoreply"
    version = "1.0.0"
    description = "关键词自动回复"
    priority = 90

    def __init__(self, handler=None):
        super().__init__(handler)
        self.rules: list = []
        self.config_path = os.path.join(os.path.dirname(__file__), "autoreply.json")
        self._load_rules()

    def _load_rules(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.rules = json.load(f)
            self.logger.info(f"[AutoReply] 加载 {len(self.rules)} 条规则")
        except Exception as e:
            self.logger.warning(f"[AutoReply] 规则加载失败: {e}")
            self.rules = []

    async def on_load(self):
        self._load_rules()

    async def on_group_message(self, event, client):
        text = event.get_text().strip()
        for rule in self.rules:
            kw = rule.get("keyword", "")
            reply = rule.get("reply", "")
            if not kw:
                continue
            if kw in text:
                await client.send(
                    SendGroupMsgAction(
                        group_id=event.group_id,
                        message=build_message(reply),
                    )
                )
                return  # 只匹配第一条

    async def on_private_message(self, event, client):
        text = event.get_text().strip()
        for rule in self.rules:
            kw = rule.get("keyword", "")
            reply = rule.get("reply", "")
            if kw and kw in text:
                await client.send(
                    SendPrivateMsgAction(
                        user_id=event.user_id,
                        message=build_message(reply),
                    )
                )
                return

    async def on_unload(self):
        self.logger.info("[AutoReply] 插件卸载")
