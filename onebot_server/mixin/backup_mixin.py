"""
backup_mixin.py — 备份 Mixin
==========================================
监听退群事件，每次退群时自动备份：
  - 白名单（群 + 好友）
  - 群列表快照
备份文件带时间戳，保留最近 N 份。
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logger import get_logger
from ..mixin_base import BaseMixin
from ..whitelist import WhitelistManager

logger = get_logger()


class BackupMixin(BaseMixin):
    """
    备份 Mixin：
    - 监听群通知事件中的 decrease（有人退群/被踢/主动退群）
    - 当机器人自己退群时，触发全量备份
    - 定期（可选）自动备份群列表
    """

    mixin_name: str = "backup"
    mixin_priority: int = 5  # 较早执行，确保其他 Mixin 看到的是最新数据

    def __init__(
        self,
        backup_dir: str = "backups",
        retention: int = 50,
        auto_backup_on_leave: bool = True,
        whitelist_manager: Optional[WhitelistManager] = None,
        **kwargs,
    ):
        self.backup_dir: str = backup_dir
        self.retention: int = retention
        self.auto_backup_on_leave: bool = auto_backup_on_leave
        self._whitelist = whitelist_manager
        # 统计
        self._backup_count: int = 0
        # 当前机器人 QQ（用于判断是否是自己退群）
        self._self_id: int = 0
        super().__init__(**kwargs)

    async def mixin_setup(self, handler: Any) -> None:
        """确保备份目录存在。"""
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
        # 从 handler 获取 whitelist 引用（如果之前没传）
        if self._whitelist is None:
            self._whitelist = getattr(handler, "whitelist", None)
        self._self_id = getattr(handler, "self_id", 0)
        logger.info(f"[BackupMixin] 初始化 | 目录={self.backup_dir} 保留={self.retention}")

    # ─── 监听退群事件 ────────────────────────────────────

    async def mixin_on_notice(self, event: Any) -> None:
        """
        监听群通知事件。
        当 notice_type=group_decrease 且退群者是自己时，触发备份。
        """
        notice_type = getattr(event, "notice_type", "")
        if notice_type != "group_decrease":
            return

        operator_id = getattr(event, "operator_id", 0)
        user_id = getattr(event, "user_id", 0)
        group_id = getattr(event, "group_id", 0)

        # 判断是否是机器人自己退群
        # user_id 是被操作者，operator_id 是操作者
        self_id = self._self_id
        is_self_leave = (user_id == self_id) or (operator_id == self_id)

        if is_self_leave:
            logger.warning(f"[BackupMixin] 检测到退群 | group={group_id} " f"user={user_id} operator={operator_id}")
            if self.auto_backup_on_leave:
                await self.backup_all(reason=f"leave_group_{group_id}")

    # ─── 核心备份方法 ────────────────────────────────────

    async def backup_all(self, reason: str = "manual") -> Optional[str]:
        """
        执行全量备份（白名单 + 群列表）。
        返回备份文件路径，失败返回 None。
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        reason_tag = reason.replace("/", "_")
        backup_name = f"backup_{timestamp}_{reason_tag}"
        backup_path = Path(self.backup_dir) / backup_name
        backup_path.mkdir(parents=True, exist_ok=True)

        try:
            # 1. 备份白名单
            if self._whitelist:
                # 群白名单
                group_data = {
                    "backup_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": reason,
                    "count": len(self._whitelist.list_groups()),
                    "items": self._whitelist.list_groups(),
                }
                with open(backup_path / "group_whitelist.json", "w", encoding="utf-8") as f:
                    json.dump(group_data, f, ensure_ascii=False, indent=2)

                # 好友白名单
                friend_data = {
                    "backup_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": reason,
                    "count": len(self._whitelist.list_friends()),
                    "items": self._whitelist.list_friends(),
                }
                with open(backup_path / "friend_whitelist.json", "w", encoding="utf-8") as f:
                    json.dump(friend_data, f, ensure_ascii=False, indent=2)

                # 群列表
                group_list = self._whitelist.get_group_list()
                list_data = {
                    "backup_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": reason,
                    "count": len(group_list),
                    "items": group_list,
                }
                with open(backup_path / "group_list.json", "w", encoding="utf-8") as f:
                    json.dump(list_data, f, ensure_ascii=False, indent=2)

            self._backup_count += 1
            logger.info(f"[BackupMixin] 备份完成 #{self._backup_count} | " f"路径={backup_path} | 原因={reason}")

            # 清理旧备份
            await self._cleanup_old_backups()

            return str(backup_path)

        except Exception as e:
            logger.error(f"[BackupMixin] 备份失败: {e}")
            # 清理半成品
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
            return None

    async def backup_whitelist_only(self, reason: str = "manual") -> Optional[str]:
        """仅备份白名单（不备份群列表）。"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"whitelist_{timestamp}_{reason}.json"
        filepath = Path(self.backup_dir) / filename

        if not self._whitelist:
            logger.warning("[BackupMixin] 无白名单管理器，跳过")
            return None

        data = {
            "backup_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
            "group_whitelist": self._whitelist.list_groups(),
            "friend_whitelist": self._whitelist.list_friends(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[BackupMixin] 白名单备份完成 | {filepath}")
        return str(filepath)

    # ─── 恢复方法 ─────────────────────────────────────────

    async def restore_from(self, backup_path: str) -> bool:
        """
        从备份目录恢复白名单和群列表。
        backup_path 是 backup_xxx 目录的路径。
        """
        path = Path(backup_path)
        if not path.exists() or not path.is_dir():
            logger.error(f"[BackupMixin] 备份路径不存在: {backup_path}")
            return False

        if not self._whitelist:
            logger.error("[BackupMixin] 无白名单管理器，无法恢复")
            return False

        try:
            # 恢复群白名单
            gw_file = path / "group_whitelist.json"
            if gw_file.exists():
                with open(gw_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._whitelist.import_groups(data.get("items", []))

            # 恢复群列表
            gl_file = path / "group_list.json"
            if gl_file.exists():
                with open(gl_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._whitelist.update_group_list(data.get("items", []))

            logger.info(f"[BackupMixin] 恢复完成 | 来源={backup_path}")
            return True
        except Exception as e:
            logger.error(f"[BackupMixin] 恢复失败: {e}")
            return False

    # ─── 列出备份 ─────────────────────────────────────────

    def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有备份目录。"""
        backup_root = Path(self.backup_dir)
        if not backup_root.exists():
            return []

        backups = []
        for item in sorted(backup_root.iterdir(), reverse=True):
            if item.is_dir() and item.name.startswith("backup_"):
                # 读取备份元信息
                info: Dict[str, Any] = {
                    "name": item.name,
                    "path": str(item),
                    "time": item.stat().st_mtime,
                }
                # 尝试读取白名单文件获取详细信息
                gw = item / "group_whitelist.json"
                if gw.exists():
                    try:
                        with open(gw, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        info["reason"] = data.get("reason", "unknown")
                        info["group_count"] = data.get("count", 0)
                    except Exception:
                        pass
                backups.append(info)

        return backups

    # ─── 内部方法 ─────────────────────────────────────────

    async def _cleanup_old_backups(self) -> None:
        """清理超出保留数量的旧备份。"""
        backups = self.list_backups()
        if len(backups) <= self.retention:
            return

        to_remove = backups[self.retention :]
        for item in to_remove:
            path = Path(item["path"])
            try:
                shutil.rmtree(path)
                logger.debug(f"[BackupMixin] 清理旧备份: {path.name}")
            except Exception as e:
                logger.warning(f"[BackupMixin] 清理失败 {path}: {e}")

    # ─── 关闭时备份 ───────────────────────────────────────

    async def mixin_teardown(self) -> None:
        logger.info(f"[BackupMixin] 统计 | 总备份次数={self._backup_count}")
        # 关闭前做一次备份
        if self._whitelist and self.auto_backup_on_leave:
            await self.backup_all(reason="shutdown")
