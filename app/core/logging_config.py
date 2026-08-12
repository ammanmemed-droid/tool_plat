"""统一日志配置：JSON / text 双格式、单一 stdout handler、自动注入 trace_id。

设计约束（第一批日志改造）：
1. 结构化输出只序列化白名单字段，绝不整体 dump LogRecord.__dict__；
2. message 去除换行与控制字符并限长，避免日志注入与大对象写盘；
3. 只输出 stdout，不在容器内创建业务日志文件；
4. configure_logging() 幂等，重复调用不会重复挂 handler。
"""
import json
import logging
import math
import re
import sys
import traceback
from datetime import datetime
from typing import Any

from app.core.responses import trace_id_ctx

# 结构化日志允许输出的扩展字段及其值类型（设计 §9.1）。
# 只白名单字段名不够：调用方可能把 Pydantic 模型、请求/响应对象塞进白名单键，
# 因此这里同时限定为标量类型，容器与任意业务对象一律丢弃。
EXTRA_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "event": (str,),
    "tool_name": (str,),
    "status": (str,),
    "http_method": (str,),
    "http_path": (str,),
    "client_ip": (str,),
    "http_status": (int,),
    "business_code": (int,),
    "duration_ms": (int, float),
    "request_bytes": (int,),
    "response_bytes": (int,),
    "dtc_count": (int,),
    "error_type": (str,),
    "request_body": (str,),
    "request_body_status": (str,),
    "request_body_truncated": (bool,),
    "rag_request_body": (str,),
    "rag_response_body": (str,),
}
EXTRA_FIELDS: tuple[str, ...] = tuple(EXTRA_FIELD_TYPES)

DEFAULT_MESSAGE_MAX_LENGTH = 1024
DEFAULT_REQUEST_BODY_MAX_BYTES = 65536
# 字段值（非 message）的长度上限：tool_name、http_path 等取自 URL，需防注入与超长
FIELD_MAX_LENGTH = 256
# 安全堆栈保留的最大帧数
STACK_MAX_FRAMES = 30
TRUNCATED_SUFFIX = "...(truncated)"
TEXT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# text 格式的字段简称，未列出的字段沿用原名
TEXT_FIELD_ALIASES = {"tool_name": "tool"}

# 标记本模块托管的 handler，用于重复配置时复用而不是叠加
_MANAGED_HANDLER_FLAG = "_roxie_managed"
# 需要收敛到 root handler 的 logger（历史上各自挂过 handler）
_MANAGED_LOGGERS = ("app", "uvicorn", "uvicorn.error", "uvicorn.access")
# 第三方库降噪：最低保持 WARNING，避免逐请求刷屏
_QUIET_LOGGERS = ("httpx", "httpcore")

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(value: str, max_length: int) -> str:
    """删除换行与控制字符并限长，防止日志注入与超长写入（设计 §9.3）。"""
    cleaned = _CONTROL_CHARS.sub("", value.replace("\r", " ").replace("\n", " "))
    if 0 < max_length < len(cleaned):
        cleaned = cleaned[:max_length] + TRUNCATED_SUFFIX
    return cleaned


def _truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]:
    """按 UTF-8 字节上限截断字符串，不保留被截断的半个字符。"""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def _text_or_none(value: Any) -> str | None:
    """公共字段只接受字符串，其余一律记为 None，不做任意对象序列化。"""
    return _sanitize_text(value, FIELD_MAX_LENGTH) if isinstance(value, str) else None


def _safe_message(record: logging.LogRecord, max_length: int) -> str:
    """格式化 message 并做安全处理（设计 §9.3）。"""
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001 - 日志本身不能因格式化失败而中断请求
        message = str(record.msg)
    return _sanitize_text(message, max_length)


def _scalar_value(field: str, value: Any) -> Any | None:
    """校验白名单字段的值类型，不满足标量约定时返回 None（该字段被省略）。"""
    if isinstance(value, bool) or not isinstance(value, EXTRA_FIELD_TYPES[field]):
        return None
    if isinstance(value, str):
        return _sanitize_text(value, FIELD_MAX_LENGTH)
    if isinstance(value, float) and not math.isfinite(value):
        # NaN / Infinity 不是合法 JSON
        return None
    return value


def _extra_fields(
    record: logging.LogRecord,
    max_request_body_bytes: int = DEFAULT_REQUEST_BODY_MAX_BYTES,
) -> dict[str, Any]:
    """按字段名与值类型双重白名单提取扩展字段，顺序固定便于采集侧对齐。"""
    fields: dict[str, Any] = {}
    formatter_truncated = False
    for field in EXTRA_FIELDS:
        value = getattr(record, field, None)
        if value is None:
            continue
        if field in ("request_body", "rag_request_body", "rag_response_body"):
            if not isinstance(value, str):
                continue
            cleaned = _sanitize_text(value, 0)
            safe_body, formatter_truncated = _truncate_utf8(
                cleaned, max(1, int(max_request_body_bytes))
            )
            fields[field] = safe_body
            continue
        if field == "request_body_truncated":
            if isinstance(value, bool):
                fields[field] = value or formatter_truncated
            continue
        safe = _scalar_value(field, value)
        if safe is not None:
            fields[field] = safe
    if formatter_truncated and "request_body_truncated" not in fields:
        fields["request_body_truncated"] = True
    return fields


def _safe_stack(exc_info: tuple) -> str:
    """安全堆栈：只输出异常类型与调用帧位置。

    绝不输出异常 value——业务或第三方库可能抛出携带 Token、VIN、request_id、
    请求参数或上游响应正文的异常（设计 §9.2、§15）。
    """
    exc_type, exc, exc_tb = exc_info
    lines: list[str] = []
    seen: set[int] = set()
    while exc_type is not None:
        lines.append(f"{'caused by ' if lines else ''}{exc_type.__qualname__}")
        lines.extend(
            f"  at {frame.filename}:{frame.lineno} in {frame.name}"
            for frame in traceback.extract_tb(exc_tb)[-STACK_MAX_FRAMES:]
        )
        if exc is None or id(exc) in seen:
            break
        seen.add(id(exc))
        nested = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
        if nested is None:
            break
        exc, exc_type, exc_tb = nested, type(nested), nested.__traceback__
    return "\n".join(lines)


class ContextFilter(logging.Filter):
    """为每条日志注入 service、version 与当前请求 trace_id。"""

    def __init__(self, service: str, version: str) -> None:
        super().__init__()
        self.service = _sanitize_text(str(service), FIELD_MAX_LENGTH)
        self.version = _sanitize_text(str(version), FIELD_MAX_LENGTH)

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        record.version = self.version
        # 启动日志与 Nacos 后台日志没有 HTTP 上下文，trace_id 为 None
        trace_id = trace_id_ctx.get()
        record.trace_id = (
            _sanitize_text(trace_id, FIELD_MAX_LENGTH) if isinstance(trace_id, str) else None
        )
        return True


class JsonFormatter(logging.Formatter):
    """单行 JSON 输出，供生产环境日志采集直接解析。"""

    def __init__(
        self,
        *,
        max_message_length: int = DEFAULT_MESSAGE_MAX_LENGTH,
        max_request_body_bytes: int = DEFAULT_REQUEST_BODY_MAX_BYTES,
        include_caller: bool = False,
    ) -> None:
        super().__init__()
        self.max_message_length = max_message_length
        self.max_request_body_bytes = max(1, int(max_request_body_bytes))
        self.include_caller = include_caller

    def formatException(self, exc_info: tuple) -> str:  # noqa: N802 - 覆盖标准库钩子
        return _safe_stack(exc_info)

    def format(self, record: logging.LogRecord) -> str:
        # 所有取值都显式收敛为 str / int / float / None，因此不需要 json 的 default 兜底，
        # 避免任意业务对象被 default=str 序列化进日志（设计 §12.1）
        payload: dict[str, Any] = {
            "timestamp": str(
                datetime.fromtimestamp(record.created).astimezone().isoformat(
                    timespec="milliseconds"
                )
            ),
            "level": str(record.levelname),
            "service": _text_or_none(getattr(record, "service", None)),
            "version": _text_or_none(getattr(record, "version", None)),
            "logger": str(record.name),
            "trace_id": _text_or_none(getattr(record, "trace_id", None)),
            "message": _safe_message(record, self.max_message_length),
        }
        payload.update(_extra_fields(record, self.max_request_body_bytes))
        if self.include_caller:
            payload["caller"] = f"{record.module}:{record.lineno}"
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None:
                payload.setdefault("error_type", exc_type.__qualname__)
            # 堆栈单独成字段，json.dumps 会转义换行，整条日志仍为单行
            payload["stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """本地开发用文本格式，字段与事件名与 JSON 保持一致。

    与设计 §12.2 示例的两处经评审接受的展示差异：输出完整 trace_id（便于精确检索，
    与 JSON 字段一致）并保留 `[logger]`（沿用改造前的文本格式，便于定位模块）。
    """

    def __init__(
        self,
        *,
        max_message_length: int = DEFAULT_MESSAGE_MAX_LENGTH,
        max_request_body_bytes: int = DEFAULT_REQUEST_BODY_MAX_BYTES,
        include_caller: bool = False,
    ) -> None:
        super().__init__(datefmt=TEXT_TIME_FORMAT)
        self.max_message_length = max_message_length
        self.max_request_body_bytes = max(1, int(max_request_body_bytes))
        self.include_caller = include_caller

    def formatException(self, exc_info: tuple) -> str:  # noqa: N802 - 覆盖标准库钩子
        return _safe_stack(exc_info)

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            self.formatTime(record, self.datefmt),
            record.levelname,
            f"[{record.name}]",
            f"trace={_text_or_none(getattr(record, 'trace_id', None))}",
        ]
        parts.extend(
            f"{TEXT_FIELD_ALIASES.get(field, field)}={value}"
            for field, value in _extra_fields(record, self.max_request_body_bytes).items()
        )
        if self.include_caller:
            parts.append(f"caller={record.module}:{record.lineno}")
        parts.append(_safe_message(record, self.max_message_length))
        line = " ".join(parts)
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def _resolve_level(level: str) -> int:
    """把配置里的级别名解析为 logging 数值，非法值回退 INFO。"""
    resolved = logging.getLevelNamesMapping().get(str(level).upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def _build_formatter(settings: Any) -> logging.Formatter:
    formatter_cls = TextFormatter if str(settings.log_format).lower() == "text" else JsonFormatter
    return formatter_cls(
        max_message_length=settings.log_message_max_length,
        max_request_body_bytes=max(
            1,
            int(
                getattr(
                    settings,
                    "log_request_body_max_bytes",
                    DEFAULT_REQUEST_BODY_MAX_BYTES,
                )
            ),
        ),
        include_caller=settings.log_include_caller,
    )


def managed_handlers() -> list[logging.Handler]:
    """返回本模块托管的 root handler。

    只托管自己创建的 handler：外部（测试框架、宿主进程）自行挂载的 handler 不删除也不复用。
    服务入口不存在并行 handler——uvicorn.run 传 log_config=None，uvicorn CLI 配置的是
    uvicorn.* 而非 root，且会被 configure_logging() 收敛为 propagate。
    """
    return [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, _MANAGED_HANDLER_FLAG, False)
    ]


def configure_logging(settings: Any) -> None:
    """统一配置 root / app / uvicorn / 第三方 logger，重复调用不会重复挂 handler。"""
    level = _resolve_level(settings.log_level)

    root = logging.getLogger()
    existing_handlers = managed_handlers()
    handler = existing_handlers[0] if existing_handlers else None
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        setattr(handler, _MANAGED_HANDLER_FLAG, True)
        root.addHandler(handler)
    handler.setLevel(level)
    handler.setFormatter(_build_formatter(settings))
    for existing in list(handler.filters):
        handler.removeFilter(existing)
    handler.addFilter(ContextFilter(settings.app_name, settings.app_version))

    root.setLevel(level)

    # 应用与 uvicorn 日志一律经 root handler 输出，取消各自的手工 handler
    for name in _MANAGED_LOGGERS:
        managed = logging.getLogger(name)
        for stale in list(managed.handlers):
            managed.removeHandler(stale)
        managed.setLevel(logging.NOTSET)
        managed.propagate = True

    logging.getLogger("uvicorn.access").disabled = not settings.access_log_enabled
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))


def get_app_logger(name: str) -> logging.Logger:
    """业务模块取 logger；handler 与格式统一由 configure_logging() 负责。"""
    return logging.getLogger(name)
