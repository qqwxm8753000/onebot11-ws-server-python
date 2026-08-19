"""
config.py — TOML 配置文件加载与热重载
==========================================
负责读取 config.toml，提供类型安全的配置访问，
并支持运行时重新加载（冷重载配置）。
"""

import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Python 3.11+ 内置 tomllib，低版本用 tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# 包内目录的绝对路径（解决"外部也有 extensions/mixin"的问题）
_PACKAGE_DIR: Path = Path(__file__).resolve().parent


class Config:
    """配置管理类，线程安全，支持热重载。"""

    def __init__(self, config_path: str = "config.toml"):
        self._config_path: Path = Path(config_path)
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._last_mtime: float = 0.0
        self.reload()

    # ─── 基础操作 ────────────────────────────────────────────

    def reload(self) -> bool:
        """重新从磁盘加载配置文件。返回是否成功。"""
        with self._lock:
            try:
                mtime = self._config_path.stat().st_mtime
                with open(self._config_path, "rb") as f:
                    self._data = tomllib.load(f)
                self._last_mtime = mtime
                return True
            except Exception as e:
                # 加载失败时保留旧配置，仅打印错误
                print(f"[Config] 加载失败: {e}", file=sys.stderr)
                return False

    def is_modified(self) -> bool:
        """检测配置文件是否被外部修改。"""
        try:
            return self._config_path.stat().st_mtime > self._last_mtime
        except OSError:
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号分隔的多级路径。
        例: config.get("server.port", 8765)
        """
        with self._lock:
            node: Any = self._data
            for part in key.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    return default
            return node

    def set(self, key: str, value: Any) -> None:
        """运行时修改配置项（不写回文件）。"""
        with self._lock:
            parts = key.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value

    def to_dict(self) -> Dict[str, Any]:
        """返回配置的深拷贝字典。"""
        import copy

        with self._lock:
            return copy.deepcopy(self._data)

    # ─── 便捷属性 ────────────────────────────────────────────

    @property
    def server_host(self) -> str:
        return self.get("server.host", "127.0.0.1")

    @property
    def server_port(self) -> int:
        return int(self.get("server.port", 8765))

    @property
    def server_path(self) -> str:
        return self.get("server.path", "/")

    @property
    def access_token(self) -> str:
        return self.get("server.access_token", "")

    @property
    def heartbeat_timeout(self) -> int:
        return int(self.get("server.heartbeat_timeout", 60))

    @property
    def action_timeout(self) -> int:
        return int(self.get("server.action_timeout", 10))

    @property
    def log_level(self) -> str:
        return self.get("logging.level", "INFO")

    @property
    def log_dir(self) -> str:
        return self.get("logging.log_dir", "logs")

    @property
    def log_console(self) -> bool:
        return bool(self.get("logging.console", True))

    @property
    def log_max_size(self) -> int:
        return int(self.get("logging.max_size", 10))

    @property
    def log_retention(self) -> int:
        return int(self.get("logging.retention", 30))

    @property
    def admin_qq(self) -> List[int]:
        return list(self.get("admin.admin_qq", []))

    @property
    def confirm_timeout(self) -> int:
        return int(self.get("admin.confirm_timeout", 300))

    @property
    def backup_dir(self) -> str:
        return self.get("backup.backup_dir", "backups")

    @property
    def auto_backup_on_leave(self) -> bool:
        return bool(self.get("backup.auto_backup_on_leave", True))

    @property
    def backup_retention(self) -> int:
        return int(self.get("backup.backup_retention", 50))

    @property
    def ext_dir(self) -> str:
        # 默认指向包内 extensions/ 目录，避免污染项目根目录
        default = str(_PACKAGE_DIR / "extensions")
        val = self.get("extension.ext_dir", default)
        # 如果是相对路径，转为基于包目录的绝对路径
        p = Path(val)
        if not p.is_absolute():
            p = _PACKAGE_DIR / p
        return str(p)

    @property
    def hot_reload(self) -> bool:
        return bool(self.get("extension.hot_reload", True))

    @property
    def watch_interval(self) -> int:
        return int(self.get("extension.watch_interval", 2))

    @property
    def ext_suffix(self) -> str:
        return self.get("extension.ext_suffix", ".py")

    @property
    def mixin_dir(self) -> str:
        # 默认指向包内 mixin/ 目录
        default = str(_PACKAGE_DIR / "mixin")
        val = self.get("mixin.mixin_dir", default)
        p = Path(val)
        if not p.is_absolute():
            p = _PACKAGE_DIR / p
        return str(p)

    @property
    def auto_load_mixins(self) -> List[str]:
        return list(self.get("mixin.auto_load", []))


# ─── 全局单例 ────────────────────────────────────────────────
_config_instance: Optional[Config] = None


def get_config(config_path: str = "config.toml") -> Config:
    """获取全局配置单例。"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance


def reset_config():
    """重置全局配置（主要用于测试）。"""
    global _config_instance
    _config_instance = None
