"""
extension_manager.py — Extension 管理器
==========================================
负责：
  - 扫描 extensions/ 目录
  - 热加载（运行时动态 importlib）
  - 热卸载（从 sys.modules 移除 + 调用 ext_unload）
  - 冷加载（首次启动加载全部）
  - 冷卸载（关闭时全部卸载）
  - 文件监控（修改自动热重载）
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type

from .extension_base import BaseExtension
from .logger import get_logger
from .mixin_base import BaseMixin

logger = get_logger()


class ExtensionManager:
    """
    Extension 管理器。
    四种加载模式：
      1. 冷加载 (cold_load_all) — 首次启动扫描目录全部加载
      2. 热加载 (hot_load)     — 运行时动态加载单个
      3. 热卸载 (hot_unload)   — 运行时动态卸载单个
      4. 冷卸载 (cold_unload_all) — 关闭时全部卸载
    """

    def __init__(
        self,
        ext_dir: str = "extensions",
        handler: Any = None,
        watch_interval: int = 2,
        ext_suffix: str = ".py",
    ):
        self.ext_dir: str = ext_dir
        self.handler: Any = handler
        self.watch_interval: int = watch_interval
        self.ext_suffix: str = ext_suffix

        # 已加载的插件: name → instance
        self._extensions: Dict[str, BaseExtension] = {}
        # 已加载的插件: name → module name（用于 sys.modules 清理）
        self._module_names: Dict[str, str] = {}
        # 文件修改时间缓存
        self._file_mtimes: Dict[str, float] = {}
        # 监控任务
        self._watch_task: Optional[asyncio.Task] = None
        self._watching: bool = False

        # 确保目录存在
        Path(self.ext_dir).mkdir(parents=True, exist_ok=True)

    # ═════════════════════════════════════════════════
    # 冷加载 / 冷卸载
    # ═════════════════════════════════════════════════

    async def cold_load_all(self) -> int:
        """
        冷加载：扫描目录，加载所有插件文件。
        返回成功加载数量。
        """
        ext_path = Path(self.ext_dir)
        if not ext_path.exists():
            logger.warning(f"[ExtMgr] 插件目录不存在: {self.ext_dir}")
            return 0

        # 发现所有插件文件
        files = sorted(ext_path.glob(f"*{self.ext_suffix}"))
        loaded = 0
        for f in files:
            name = f.stem
            if name.startswith("_"):
                continue
            ok = await self._load_one(name, f)
            if ok:
                loaded += 1

        logger.info(f"[ExtMgr] 冷加载完成: {loaded}/{len(files)} 个插件")
        return loaded

    async def cold_unload_all(self) -> int:
        """
        冷卸载：关闭时卸载所有插件（逆序）。
        返回成功卸载数量。
        """
        names = list(self._extensions.keys())
        unloaded = 0
        for name in reversed(names):  # 逆序卸载（后加载的先卸）
            ok = await self._unload_one(name)
            if ok:
                unloaded += 1

        logger.info(f"[ExtMgr] 冷卸载完成: {unloaded}/{len(names)} 个插件")
        return unloaded

    # ═════════════════════════════════════════════════
    # 热加载 / 热卸载
    # ═════════════════════════════════════════════════

    async def hot_load(self, name: str) -> bool:
        """
        热加载：运行时动态加载单个插件。
        如果已加载则先卸载再加载（= 热重载）。
        """
        filepath = Path(self.ext_dir) / f"{name}{self.ext_suffix}"
        if not filepath.exists():
            logger.error(f"[ExtMgr] 热加载失败: 文件不存在 {filepath}")
            return False

        # 如果已加载，先卸载
        if name in self._extensions:
            await self._unload_one(name)

        return await self._load_one(name, filepath)

    async def hot_unload(self, name: str) -> bool:
        """
        热卸载：运行时动态卸载单个插件。
        """
        if name not in self._extensions:
            logger.warning(f"[ExtMgr] 热卸载失败: {name} 未加载")
            return False

        return await self._unload_one(name)

    async def hot_reload(self, name: str) -> bool:
        """
        热重载 = 热卸载 + 热加载。
        """
        # 先卸载（如果存在）
        if name in self._extensions:
            await self._unload_one(name)
        # 再加载
        filepath = Path(self.ext_dir) / f"{name}{self.ext_suffix}"
        if not filepath.exists():
            logger.error(f"[ExtMgr] 热重载失败: 文件不存在 {filepath}")
            return False
        return await self._load_one(name, filepath)

    # ═════════════════════════════════════════════════
    # 便捷别名（兼容不同命名风格）
    # ═════════════════════════════════════════════════

    async def load(self, name: str) -> bool:
        """别名：等同于 hot_load。"""
        return await self.hot_load(name)

    async def unload(self, name: str) -> bool:
        """别名：等同于 hot_unload。"""
        return await self.hot_unload(name)

    # ═════════════════════════════════════════════════
    # 内部加载/卸载逻辑
    # ═════════════════════════════════════════════════

    async def _load_one(self, name: str, filepath: Path) -> bool:
        """
        加载单个插件文件。
        1. 动态 import 模块
        2. 查找 BaseExtension 子类
        3. 实例化并调用 ext_load
        4. 注册到 handler 的 Extension 列表
        """
        try:
            # 动态导入（每次用唯一模块名避免缓存冲突）
            module_name = f"_ext_{name}_{int(time.time() * 1000)}"
            spec = importlib.util.spec_from_file_location(module_name, str(filepath))
            if not spec or not spec.loader:
                logger.error(f"[ExtMgr] 无法创建模块 spec: {name}")
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找 Extension 类
            ext_class: Optional[Type[BaseExtension]] = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseExtension) and attr is not BaseExtension:
                    ext_class = attr
                    break

            if not ext_class:
                logger.error(f"[ExtMgr] 加载失败: {name} 中未找到 BaseExtension 子类")
                del sys.modules[module_name]
                return False

            # 实例化
            ext_instance = ext_class()

            # 验证：Extension 只能继承 BaseMixin 的子类，不能直接持有 WebSocket
            self._validate_extension(ext_instance, name)

            # 调用加载钩子
            handler = self.handler
            ok = await ext_instance.ext_load(handler)
            if not ok:
                logger.error(f"[ExtMgr] {name} ext_load 返回 False")
                del sys.modules[module_name]
                return False

            # 注册
            self._extensions[name] = ext_instance
            self._module_names[name] = module_name
            self._file_mtimes[str(filepath)] = filepath.stat().st_mtime

            # 注册到 handler 的 extension 列表
            if handler and hasattr(handler, "add_extension"):
                handler.add_extension(name, ext_instance)

            logger.info(f"[ExtMgr] ✓ 热加载成功: {name} " f"({ext_class.__name__} v{ext_instance.version})")
            return True

        except Exception as e:
            logger.error(f"[ExtMgr] 加载 {name} 异常: {e}")
            # 清理
            module_name = f"_ext_{name}_{int(time.time() * 1000)}"
            if module_name in sys.modules:
                del sys.modules[module_name]
            return False

    async def _unload_one(self, name: str) -> bool:
        """
        卸载单个插件。
        1. 调用 ext_unload
        2. 从 handler 移除
        3. 从 sys.modules 删除
        """
        ext = self._extensions.get(name)
        if not ext:
            return False

        try:
            # 调用卸载钩子
            await ext.ext_unload()

            # 从 handler 移除
            handler = self.handler
            if handler and hasattr(handler, "remove_extension"):
                handler.remove_extension(name)

            # 清理模块
            mod_name = self._module_names.pop(name, "")
            if mod_name and mod_name in sys.modules:
                del sys.modules[mod_name]

            # 从注册表移除
            self._extensions.pop(name, None)

            # 清理 mtime 缓存
            to_remove = [fp for fp, mt in self._file_mtimes.items() if Path(fp).stem == name]
            for fp in to_remove:
                self._file_mtimes.pop(fp, None)

            logger.info(f"[ExtMgr] ✓ 热卸载成功: {name}")
            return True

        except Exception as e:
            logger.error(f"[ExtMgr] 卸载 {name} 异常: {e}")
            return False

    def _validate_extension(self, instance: BaseExtension, name: str) -> None:
        """
        验证 Extension 合法性：
        - 不能持有 WebSocket 直接引用
        - 只能继承 BaseMixin 及其子类
        - 不能有 _ws / _websocket / _server 属性
        """
        forbidden_attrs = ["_ws", "_websocket", "_server", "_handler_server"]
        for attr in forbidden_attrs:
            if hasattr(instance, attr) and getattr(instance, attr) is not None:
                logger.warning(f"[ExtMgr] {name} 包含敏感属性 '{attr}'，" f"Extension 不应直接操作 WebSocket")

        # 检查继承链中是否有非 Mixin 的异常基类
        allowed_bases = (BaseExtension, BaseMixin)
        for cls in instance.__class__.__mro__[1:]:  # 排除自身
            if cls in (object,):
                continue
            if not issubclass(cls, allowed_bases):
                logger.warning(f"[ExtMgr] {name} 继承了非 Mixin 类: {cls.__name__}")

    # ═════════════════════════════════════════════════
    # 文件监控（热重载）
    # ═════════════════════════════════════════════════

    async def start_watcher(self) -> None:
        """启动文件监控任务。"""
        if self._watching:
            return
        self._watching = True
        self._watch_task = asyncio.create_task(self._watch_loop())
        logger.info(f"[ExtMgr] 文件监控已启动 (间隔 {self.watch_interval}s)")

    async def stop_watcher(self) -> None:
        """停止文件监控。"""
        self._watching = False
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        logger.info("[ExtMgr] 文件监控已停止")

    async def _watch_loop(self) -> None:
        """监控循环：检测文件变更自动热重载。"""
        while self._watching:
            try:
                await asyncio.sleep(self.watch_interval)
                await self._check_changes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ExtMgr] 监控异常: {e}")

    async def _check_changes(self) -> None:
        """检查文件变更。"""
        ext_path = Path(self.ext_dir)
        if not ext_path.exists():
            return

        current_files: Set[str] = set()

        for f in ext_path.glob(f"*{self.ext_suffix}"):
            if f.stem.startswith("_"):
                continue

            current_files.add(str(f))
            name = f.stem
            mtime = f.stat().st_mtime
            old_mtime = self._file_mtimes.get(str(f), 0)

            if mtime > old_mtime and name in self._extensions:
                # 文件被修改 → 热重载
                logger.info(f"[ExtMgr] 检测到 {name} 变更，自动热重载")
                await self.hot_reload(name)
                self._file_mtimes[str(f)] = mtime
            elif name not in self._extensions:
                # 新文件 → 可选自动加载（这里不自动加载，需手动）
                self._file_mtimes[str(f)] = mtime

        # 检测已删除的文件
        for fp in list(self._file_mtimes.keys()):
            if fp not in current_files and Path(fp).stem in self._extensions:
                name = Path(fp).stem
                logger.info(f"[ExtMgr] 检测到 {name} 被删除，自动卸载")
                await self.hot_unload(name)

    # ═════════════════════════════════════════════════
    # 查询接口
    # ═════════════════════════════════════════════════

    def get(self, name: str) -> Optional[BaseExtension]:
        """获取已加载的插件实例。"""
        return self._extensions.get(name)

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有已加载插件信息。"""
        result = []
        for name, ext in self._extensions.items():
            result.append(
                {
                    "name": name,
                    "class": ext.__class__.__name__,
                    "version": getattr(ext, "version", "1.0.0"),
                    "description": getattr(ext, "description", ""),
                    "priority": getattr(ext, "priority", 100),
                    "enabled": getattr(ext, "mixin_enabled", True),
                }
            )
        # 按优先级排序
        result.sort(key=lambda x: x["priority"])
        return result

    def is_loaded(self, name: str) -> bool:
        """检查插件是否已加载。"""
        return name in self._extensions

    @property
    def count(self) -> int:
        """已加载插件数量。"""
        return len(self._extensions)
