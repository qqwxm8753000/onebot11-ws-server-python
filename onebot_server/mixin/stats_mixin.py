"""
stats_mixin.py — 消息统计 Mixin（自定义 Mixin 示例）
==========================================
演示如何编写自定义 Mixin 并继承其他 Mixin。
功能：
  - 统计每种消息类型的数量
  - 统计每个群的消息数
  - 提供 /stats 命令到控制台
  - 可被其他 Mixin 继承扩展统计维度
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Dict

from ..logger import get_logger
from ..mixin_base import BaseMixin

logger = get_logger()


class StatsMixin(BaseMixin):
    """
    消息统计 Mixin。
    继承 BaseMixin，可被其他 Mixin 继承。
    """

    mixin_name: str = "stats"
    mixin_priority: int = 3  # 在 LogMixin 之后、业务逻辑之前

    def __init__(self, top_n: int = 5):
        self.top_n: int = top_n
        # 总消息数
        self._total_messages: int = 0
        # 按消息类型统计
        self._by_type: Counter = Counter()
        # 按群统计
        self._by_group: Counter = Counter()
        # 按用户统计
        self._by_user: Counter = Counter()
        # 按小时统计
        self._by_hour: Counter = Counter()
        # 启动时间
        self._start_time: float = time.time()

    async def mixin_on_message(self, event: Any) -> None:
        """每收到一条消息就统计。"""
        self._total_messages += 1

        # 按类型
        msg_type = getattr(event, "message_type", "unknown")
        self._by_type[msg_type] += 1

        # 按群
        group_id = getattr(event, "group_id", 0)
        if group_id:
            self._by_group[group_id] += 1

        # 按用户
        user_id = getattr(event, "user_id", 0)
        if user_id:
            self._by_user[user_id] += 1

        # 按小时
        hour = time.localtime().tm_hour
        self._by_hour[hour] += 1

    # ─── 查询接口 ───────────────────────────────────────

    def get_report(self) -> Dict[str, Any]:
        """生成统计报告。"""
        uptime = time.time() - self._start_time
        return {
            "uptime_seconds": uptime,
            "total_messages": self._total_messages,
            "messages_per_minute": (self._total_messages / (uptime / 60) if uptime > 60 else 0),
            "by_type": dict(self._by_type.most_common()),
            "top_groups": self._by_group.most_common(self.top_n),
            "top_users": self._by_user.most_common(self.top_n),
            "by_hour": dict(sorted(self._by_hour.items())),
        }

    def print_report(self) -> str:
        """生成可读的统计报告。"""
        r = self.get_report()
        lines = [
            "📊 消息统计报告",
            f"  运行时间: {r['uptime_seconds']:.0f}s",
            f"  总消息数: {r['total_messages']}",
            f"  每分钟:   {r['messages_per_minute']:.1f}",
            "",
            "  按类型:",
        ]
        for t, c in r["by_type"].items():
            lines.append(f"    {t}: {c}")
        lines.append("")
        lines.append(f"  最活跃群 TOP{self.top_n}:")
        for gid, cnt in r["top_groups"]:
            lines.append(f"    {gid}: {cnt}条")
        lines.append("")
        lines.append(f"  最活跃用户 TOP{self.top_n}:")
        for uid, cnt in r["top_users"]:
            lines.append(f"    {uid}: {cnt}条")

        return "\n".join(lines)

    async def mixin_teardown(self) -> None:
        """关闭时输出统计。"""
        logger.info(f"\n{self.print_report()}")


# ═══════════════════════════════════════════════════════════
# Mixin 继承示例：StatsMixin → AdvancedStatsMixin
# ═══════════════════════════════════════════════════════════


class AdvancedStatsMixin(StatsMixin):
    """
    高级统计 Mixin：继承 StatsMixin，额外统计：
      - 图片/表情/at 消息数量
      - 平均消息长度
      - 命令使用频率
    """

    mixin_name: str = "stats_advanced"
    mixin_priority: int = 4

    def __init__(self, top_n: int = 5):
        super().__init__(top_n=top_n)
        self._image_count: int = 0
        self._face_count: int = 0
        self._at_count: int = 0
        self._total_text_length: int = 0
        self._command_count: Counter = Counter()

    async def mixin_on_message(self, event: Any) -> None:
        """覆盖父类方法，增加更多统计。"""
        # 先调用父类统计
        await super().mixin_on_message(event)

        # 统计消息段
        message = getattr(event, "message", [])
        text_parts = []
        for seg in message:
            seg_type = getattr(seg, "type", "")
            if seg_type == "image":
                self._image_count += 1
            elif seg_type == "face":
                self._face_count += 1
            elif seg_type == "at":
                self._at_count += 1
            elif seg_type == "text":
                text = getattr(seg, "data", {}).get("text", "")
                text_parts.append(text)

        # 文本长度
        full_text = "".join(text_parts).strip()
        if full_text:
            self._total_text_length += len(full_text)

        # 命令统计
        if full_text.startswith("/"):
            parts = full_text.split()
            cmd = parts[0].lower()
            self._command_count[cmd] += 1

    def print_report(self) -> str:
        """扩展报告。"""
        base_report = super().print_report()
        avg_len = self._total_text_length / self._total_messages if self._total_messages > 0 else 0
        extra = [
            "",
            "  ── 高级统计 ──",
            f"  图片消息: {self._image_count}",
            f"  表情消息: {self._face_count}",
            f"  @消息:    {self._at_count}",
            f"  平均长度: {avg_len:.1f} 字符",
            "",
            "  命令使用 TOP5:",
        ]
        for cmd, cnt in self._command_count.most_common(5):
            extra.append(f"    {cmd}: {cnt}次")

        return base_report + "\n".join(extra)
