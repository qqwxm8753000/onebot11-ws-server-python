"""
whitelist.py — 白名单管理
==========================================
管理群白名单和好友白名单，支持持久化到 JSON 文件。
白名单用于：退群确认、敏感操作授权等场景。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class WhitelistManager:
    """
    白名单管理器。
    - 群白名单：允许操作的群列表
    - 好友白名单：免审批的好友列表
    - 群列表缓存：当前所在群的信息快照
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._group_whitelist_file = self._data_dir / "group_whitelist.json"
        self._friend_whitelist_file = self._data_dir / "friend_whitelist.json"
        self._group_list_file = self._data_dir / "group_list.json"

        # 群白名单（群号集合）
        self._group_whitelist: Set[int] = set()
        # 好友白名单（QQ 号集合）
        self._friend_whitelist: Set[int] = set()
        # 群列表缓存
        self._group_list: List[Dict[str, Any]] = []

        self._load_all()

    # ─── 持久化 ────────────────────────────────────────────

    def _load_all(self) -> None:
        """从磁盘加载所有白名单和群列表。"""
        self._group_whitelist = self._load_set(self._group_whitelist_file)
        self._friend_whitelist = self._load_set(self._friend_whitelist_file)
        self._group_list = self._load_list(self._group_list_file)

    def _load_set(self, path: Path) -> Set[int]:
        """加载 JSON 文件为 int 集合。"""
        if not path.exists():
            return set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(int(x) for x in data.get("items", []))
        except (json.JSONDecodeError, OSError):
            return set()

    def _load_list(self, path: Path) -> List[Dict[str, Any]]:
        """加载 JSON 文件为列表。"""
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("items", []))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_set(self, path: Path, items: Set[int]) -> None:
        """保存集合到 JSON 文件。"""
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "items": sorted(items),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _save_list(self, path: Path, items: List[Dict[str, Any]]) -> None:
        """保存列表到 JSON 文件。"""
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "items": items,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ─── 群白名单操作 ────────────────────────────────────────

    def add_group(self, group_id: int) -> bool:
        """添加群到白名单。返回是否新增。"""
        if group_id in self._group_whitelist:
            return False
        self._group_whitelist.add(group_id)
        self._save_set(self._group_whitelist_file, self._group_whitelist)
        return True

    def remove_group(self, group_id: int) -> bool:
        """从白名单移除群。返回是否成功。"""
        if group_id not in self._group_whitelist:
            return False
        self._group_whitelist.discard(group_id)
        self._save_set(self._group_whitelist_file, self._group_whitelist)
        return True

    def is_group_whitelisted(self, group_id: int) -> bool:
        """检查群是否在白名单中。"""
        return group_id in self._group_whitelist

    def list_groups(self) -> List[int]:
        """获取所有白名单群号。"""
        return sorted(self._group_whitelist)

    # ─── 好友白名单操作 ──────────────────────────────────────

    def add_friend(self, user_id: int) -> bool:
        """添加好友到白名单。"""
        if user_id in self._friend_whitelist:
            return False
        self._friend_whitelist.add(user_id)
        self._save_set(self._friend_whitelist_file, self._friend_whitelist)
        return True

    def remove_friend(self, user_id: int) -> bool:
        """从白名单移除好友。"""
        if user_id not in self._friend_whitelist:
            return False
        self._friend_whitelist.discard(user_id)
        self._save_set(self._friend_whitelist_file, self._friend_whitelist)
        return True

    def is_friend_whitelisted(self, user_id: int) -> bool:
        """检查好友是否在白名单中。"""
        return user_id in self._friend_whitelist

    def list_friends(self) -> List[int]:
        """获取所有白名单好友 QQ 号。"""
        return sorted(self._friend_whitelist)

    # ─── 群列表缓存 ──────────────────────────────────────────

    def update_group_list(self, groups: List[Dict[str, Any]]) -> None:
        """
        更新群列表缓存。
        groups 元素格式: {"group_id": 123, "group_name": "xxx", ...}
        """
        self._group_list = list(groups)
        self._save_list(self._group_list_file, self._group_list)

    def get_group_list(self) -> List[Dict[str, Any]]:
        """获取缓存的群列表。"""
        return list(self._group_list)

    def get_group_info(self, group_id: int) -> Optional[Dict[str, Any]]:
        """查找某个群的缓存信息。"""
        for g in self._group_list:
            if int(g.get("group_id", 0)) == group_id:
                return dict(g)
        return None

    def remove_group_from_list(self, group_id: int) -> bool:
        """从群列表缓存中移除（退群时调用）。"""
        before = len(self._group_list)
        self._group_list = [g for g in self._group_list if int(g.get("group_id", 0)) != group_id]
        changed = len(self._group_list) != before
        if changed:
            self._save_list(self._group_list_file, self._group_list)
        return changed

    # ─── 批量导入导出 ────────────────────────────────────────

    def export_all(self) -> Dict[str, Any]:
        """导出全部白名单和群列表为字典。"""
        return {
            "group_whitelist": sorted(self._group_whitelist),
            "friend_whitelist": sorted(self._friend_whitelist),
            "group_list": self._group_list,
        }

    def import_groups(self, group_ids: List[int]) -> int:
        """批量导入群白名单，返回新增数量。"""
        before = len(self._group_whitelist)
        for gid in group_ids:
            self._group_whitelist.add(int(gid))
        added = len(self._group_whitelist) - before
        if added > 0:
            self._save_set(self._group_whitelist_file, self._group_whitelist)
        return added
