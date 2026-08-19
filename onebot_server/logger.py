"""
logger.py — 日志模块
==========================================
基于 loguru 封装，支持控制台彩色输出 + 文件轮转。
通过 init_logger() 根据配置初始化，全局通过 get_logger() 获取。
"""

import os
import sys

from loguru import logger as _logger

_initialized: bool = False


def init_logger(
    level: str = "INFO",
    log_dir: str = "logs",
    console: bool = True,
    max_size: int = 10,
    retention: int = 30,
) -> None:
    """
    初始化日志系统。
    - level: 日志级别（DEBUG/INFO/WARNING/ERROR）
    - log_dir: 日志目录
    - console: 是否输出到控制台
    - max_size: 单文件最大 MB
    - retention: 保留文件数
    """
    global _initialized

    # 清除默认 sink
    _logger.remove()

    # 控制台输出（带颜色）
    if console:
        _logger.add(
            sys.stderr,
            level=level.upper(),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:"
                "<cyan>{line}</cyan> - <level>{message}</level>"
            ),
            colorize=True,
            enqueue=True,
        )

    # 文件输出（按大小轮转）
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "onebot_{time:YYYY-MM-DD}.log")
    _logger.add(
        log_file,
        level=level.upper(),
        rotation=f"{max_size} MB",
        retention=retention,
        encoding="utf-8",
        enqueue=True,
        format=("{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | " "{name}:{function}:{line} - {message}"),
    )

    # 错误日志单独存档
    err_file = os.path.join(log_dir, "error_{time:YYYY-MM-DD}.log")
    _logger.add(
        err_file,
        level="ERROR",
        rotation=f"{max_size} MB",
        retention=retention,
        encoding="utf-8",
        enqueue=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | " "{name}:{function}:{line} - {message}\n" "{{extra={extra}}}"
        ),
    )

    _initialized = True
    _logger.info(f"日志系统初始化完成 | 级别={level} | 目录={log_dir}")


def get_logger():
    """获取全局 logger 实例。"""
    global _initialized
    if not _initialized:
        # 未初始化时给一个最小可用配置
        _logger.remove()
        _logger.add(sys.stderr, level="DEBUG")
        _initialized = True
    return _logger


# 导出
logger = get_logger()
