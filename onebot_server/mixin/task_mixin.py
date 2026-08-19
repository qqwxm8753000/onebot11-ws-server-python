"""
task_mixin.py — 任务调度 Mixin
==========================================
提供定时任务和周期性任务能力：
  - 添加定时任务（cron 风格或间隔秒数）
  - 任务列表查看/取消
  - 可被其他 Mixin 继承扩展
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from ..logger import get_logger
from ..mixin_base import BaseMixin

logger = get_logger()

# 任务函数类型：必须是 async 函数（协程函数）
TaskFunc = Callable[[], Any]  # 实际返回 coroutine，由调度器统一 await


class TaskMixin(BaseMixin):
    """
    任务调度 Mixin：
    - schedule_interval(): 按间隔秒数重复执行
    - schedule_once(): 延迟一次性执行
    - schedule_cron(): 类 cron 表达式执行
    - list_tasks() / cancel_task()
    """

    mixin_name: str = "task"
    mixin_priority: int = 20

    def __init__(self, **kwargs):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        super().__init__(**kwargs)

    # ─── 初始化 ─────────────────────────────────────────

    async def mixin_setup(self, handler: Any) -> None:
        self._handler = handler
        self._running = True
        # 启动调度循环
        loop = asyncio.get_event_loop()
        self._loop_task = loop.create_task(self._scheduler_loop())
        logger.info("[TaskMixin] 任务调度器已启动")

    # ─── 注册任务 ───────────────────────────────────────

    def schedule_interval(
        self,
        name: str,
        func: TaskFunc,
        interval: float,
        immediate: bool = False,
    ) -> bool:
        """
        注册间隔任务。
        - name: 任务名（唯一）
        - func: 异步函数
        - interval: 间隔秒数
        - immediate: 是否立即执行一次
        """
        if name in self._tasks:
            logger.warning(f"[TaskMixin] 任务 {name} 已存在")
            return False

        self._tasks[name] = {
            "func": func,
            "type": "interval",
            "interval": interval,
            "next_run": time.time() if immediate else time.time() + interval,
            "last_run": 0.0,
            "run_count": 0,
            "enabled": True,
        }
        logger.info(f"[TaskMixin] 注册间隔任务: {name} (每 {interval}s)")
        return True

    def schedule_once(self, name: str, func: TaskFunc, delay: float) -> bool:
        """
        注册一次性延迟任务。
        - delay: 延迟秒数
        """
        if name in self._tasks:
            return False
        self._tasks[name] = {
            "func": func,
            "type": "once",
            "next_run": time.time() + delay,
            "last_run": 0.0,
            "run_count": 0,
            "enabled": True,
        }
        logger.info(f"[TaskMixin] 注册延迟任务: {name} ({delay}s后)")
        return True

    def schedule_cron(
        self,
        name: str,
        func: TaskFunc,
        minute: str = "*",
        hour: str = "*",
        day: str = "*",
        month: str = "*",
        weekday: str = "*",
    ) -> bool:
        """
        注册类 cron 任务。
        字段支持: 数字、"*"（任意）、"*/n"（步长）。
        简化版 cron，不依赖外部库。
        """
        if name in self._tasks:
            return False

        self._tasks[name] = {
            "func": func,
            "type": "cron",
            "cron": {
                "minute": minute,
                "hour": hour,
                "day": day,
                "month": month,
                "weekday": weekday,
            },
            "next_run": time.time(),  # 首次立即检查
            "last_run": 0.0,
            "run_count": 0,
            "enabled": True,
        }
        logger.info(f"[TaskMixin] 注册Cron任务: {name} ({minute} {hour} {day} {month} {weekday})")
        return True

    # ─── 调度循环 ───────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        """主调度循环。"""
        while self._running:
            try:
                now = time.time()
                for name, task in list(self._tasks.items()):
                    if not task["enabled"]:
                        continue

                    should_run = False
                    if task["type"] == "interval":
                        should_run = now >= task["next_run"]
                    elif task["type"] == "once":
                        should_run = now >= task["next_run"]
                    elif task["type"] == "cron":
                        if now >= task["next_run"]:
                            should_run = self._match_cron(now, task["cron"])

                    if should_run:
                        await self._execute_task(name, task)

                await asyncio.sleep(1)  # 1秒精度
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TaskMixin] 调度循环错误: {e}")
                await asyncio.sleep(5)

    async def _execute_task(self, name: str, task: Dict[str, Any]) -> None:
        """执行任务并处理异常。

        注意：所有注册的任务函数必须是 async 函数（协程）。
        统一用 await 调用，避免 isawaitable 在部分 Python 版本下的兼容问题。
        """
        func = task["func"]
        try:
            logger.debug(f"[TaskMixin] 执行任务: {name}")
            # 直接 await —— 注册时就必须传 async 函数
            await func()
            task["run_count"] += 1
            task["last_run"] = time.time()

            # 更新下次运行时间
            if task["type"] == "interval":
                task["next_run"] = time.time() + task["interval"]
            elif task["type"] == "once":
                task["enabled"] = False  # 一次性，执行后禁用
                del self._tasks[name]
            elif task["type"] == "cron":
                # cron 下一分钟再检查
                task["next_run"] = time.time() + 60

        except Exception as e:
            logger.error(f"[TaskMixin] 任务 {name} 执行失败: {e}")

    def _match_cron(self, now: float, cron: Dict[str, str]) -> bool:
        """简化的 cron 匹配（按当前时间）。"""
        t = time.localtime(now)
        checks = [
            (t.tm_min, cron["minute"]),
            (t.tm_hour, cron["hour"]),
            (t.tm_mday, cron["day"]),
            (t.tm_mon, cron["month"]),
            (t.tm_wday, cron["weekday"]),
        ]
        for value, pattern in checks:
            if pattern == "*":
                continue
            if pattern.startswith("*/"):
                step = int(pattern[2:])
                if value % step != 0:
                    return False
            else:
                if value != int(pattern):
                    return False
        return True

    # ─── 任务管理 ───────────────────────────────────────

    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务。"""
        result = []
        now = time.time()
        for name, task in self._tasks.items():
            info = {
                "name": name,
                "type": task["type"],
                "enabled": task["enabled"],
                "run_count": task["run_count"],
                "last_run": (
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task["last_run"]))
                    if task["last_run"] > 0
                    else "从未"
                ),
            }
            if task["type"] == "interval":
                info["interval"] = f"{task['interval']}s"
                info["next_in"] = f"{max(0, task['next_run'] - now):.0f}s"
            elif task["type"] == "once":
                info["runs_in"] = f"{max(0, task['next_run'] - now):.0f}s"
            elif task["type"] == "cron":
                info["cron"] = task["cron"]
            result.append(info)
        return result

    def cancel_task(self, name: str) -> bool:
        """取消任务。"""
        if name in self._tasks:
            del self._tasks[name]
            logger.info(f"[TaskMixin] 取消任务: {name}")
            return True
        return False

    def enable_task(self, name: str, enabled: bool = True) -> bool:
        """启用/禁用任务。"""
        if name in self._tasks:
            self._tasks[name]["enabled"] = enabled
            return True
        return False

    # ─── 关闭 ───────────────────────────────────────────

    async def mixin_teardown(self) -> None:
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("[TaskMixin] 任务调度器已关闭")
