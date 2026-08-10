"""统一日志配置：确保 uvicorn 与应用 app.* 日志都输出到控制台。"""
import logging
import sys
from typing import Any

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": LOG_FORMAT,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "access": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["default"],
    },
    "loggers": {
        "app": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}


def get_app_logger(name: str) -> logging.Logger:
    """为业务模块绑定 stdout handler，避免 uvicorn 覆盖 logging 配置后日志丢失。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
