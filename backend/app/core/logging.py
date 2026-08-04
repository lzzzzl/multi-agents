"""统一日志配置。"""

import logging
import sys


def setup_logging() -> None:
    """配置根 logger,输出到 stdout,带时间、级别和模块。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # 降低第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
