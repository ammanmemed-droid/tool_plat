# Invoke Request Body Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 Agent、Tool 和 RAG 接口行为的前提下，可配置地记录 `/api/v1/tools/{tool_name}/invoke` 收到的完整 JSON 入参。

**Architecture:** 复用现有 HTTP middleware 已解析的 JSON，请求体先紧凑序列化为单行字符串，再按 UTF-8 字节边界截断并写入请求日志事件。日志格式化器对请求体字段实施第二层类型和长度防护；功能默认关闭，完成摘要日志保持不变。

**Tech Stack:** Python 3.13、FastAPI、Pydantic Settings、Python `logging`、pytest。

## Global Constraints

- 仅处理 `POST /api/v1/tools/{tool_name}/invoke`。
- 不记录 Header、Authorization、Cookie、Query、RAG 请求/响应或 Tool 返回正文。
- `LOG_INCLUDE_REQUEST_BODY=false`，默认不记录请求体。
- `LOG_REQUEST_BODY_MAX_BYTES=65536`，只限制日志，不限制或修改业务请求。
- `request_body` 固定为紧凑单行 JSON 字符串，保留字段名、值、对象字段顺序和数组顺序。
- 截断必须位于 UTF-8 字符边界，外层 JSON 日志必须始终合法。
- 不修改 Tool Schema、接口模型、响应信封、echo、RAG 转发、服务发现和 Dockerfile。
- 遵循用户现有交付习惯：新增测试文件只用于开发验证，最终从工作树删除，不进入部署代码提交。

---

## File Structure

- `app/config.py`：声明请求体日志开关和最大字节数。
- `.env.example`：提供默认关闭的部署配置示例。
- `app/core/log_context.py`：保存当前请求已序列化、已限长的日志字符串及状态，不保存原始对象。
- `app/core/logging_config.py`：对白名单字段 `request_body`、状态和截断标记做格式化层防护。
- `app/main.py`：在现有 middleware 的 `/invoke` JSON 解析位置生成并输出请求事件。
- `tests/test_invoke_request_body_logging.py`：开发期临时回归测试；全部验证通过后删除，不提交。

### Task 1: 配置与日志格式化边界

**Files:**
- Modify: `app/config.py:62-72`
- Modify: `.env.example:33-39`
- Modify: `app/core/log_context.py:21-29`
- Modify: `app/core/logging_config.py:20-103,150-245`
- Create temporarily: `tests/test_invoke_request_body_logging.py`

**Interfaces:**
- Produces: `Settings.log_include_request_body: bool`
- Produces: `Settings.log_request_body_max_bytes: int`
- Produces: `RequestLogContext.request_body: str | None`
- Produces: `RequestLogContext.request_body_status: str | None`
- Produces: `RequestLogContext.request_body_truncated: bool`
- Produces: `_truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]`

- [ ] **Step 1: 写配置与 Formatter 的失败测试**

在临时测试文件中先加入：

```python
import json
import logging

from app.config import Settings
from app.core.logging_config import JsonFormatter, TextFormatter, _truncate_utf8


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "收到请求", (), None)
    record.service = "roxie-router-service"
    record.version = "0.1.0"
    record.trace_id = "trace-001"
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_request_body_logging_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.log_include_request_body is False
    assert settings.log_request_body_max_bytes == 65536


def test_truncate_utf8_does_not_split_chinese_character() -> None:
    value, truncated = _truncate_utf8("丰田ABC", 7)
    assert value == "丰田A"
    assert truncated is True
    assert len(value.encode("utf-8")) <= 7


def test_json_formatter_keeps_request_body_as_a_string_and_single_line() -> None:
    body = '{"arguments":{"brand":"丰田"}}'
    line = JsonFormatter(max_request_body_bytes=65536).format(
        _record(
            event="tool.invoke.request",
            request_body=body,
            request_body_truncated=False,
        )
    )
    payload = json.loads(line)
    assert "\n" not in line
    assert payload["request_body"] == body
    assert payload["request_body_truncated"] is False


def test_formatter_enforces_its_own_request_body_byte_limit() -> None:
    line = JsonFormatter(max_request_body_bytes=7).format(
        _record(event="tool.invoke.request", request_body="丰田ABC")
    )
    payload = json.loads(line)
    assert payload["request_body"] == "丰田A"
    assert payload["request_body_truncated"] is True


def test_text_formatter_outputs_request_body_on_one_line() -> None:
    line = TextFormatter(max_request_body_bytes=65536).format(
        _record(event="tool.invoke.request", request_body='{"text":"a\\nb"}')
    )
    assert line.count("\n") == 0
    assert 'request_body={"text":"a\\nb"}' in line
```

- [ ] **Step 2: 运行定向测试并确认失败原因**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest tests\test_invoke_request_body_logging.py -q
```

Expected: FAIL，原因是新配置、`_truncate_utf8` 和 Formatter 参数尚不存在。

- [ ] **Step 3: 增加配置字段与示例**

在 `Settings` 日志配置区域加入：

```python
    # 是否记录 Tool invoke 收到的完整 JSON 入参；生产环境需明确开启
    log_include_request_body: bool = False
    # 请求体日志最大 UTF-8 字节数，仅限制日志，不限制业务请求
    log_request_body_max_bytes: int = 65536
```

在 `.env.example` 日志区域加入：

```dotenv
# 是否记录 POST /api/v1/tools/{tool_name}/invoke 的完整 JSON 入参
LOG_INCLUDE_REQUEST_BODY=false
# 单条请求体日志最大 UTF-8 字节数（默认 64 KiB）
LOG_REQUEST_BODY_MAX_BYTES=65536
```

- [ ] **Step 4: 扩展请求日志上下文**

在 `RequestLogContext` 增加以下字段，只保存处理后的日志数据：

```python
    request_body: str | None = None
    request_body_status: str | None = None
    request_body_truncated: bool = False
```

同步更新模块和 dataclass 注释，明确请求体是显式开启后才保存的紧凑、限长字符串，不是原始 Python 对象。

- [ ] **Step 5: 实现 UTF-8 截断与 Formatter 二次防护**

在 `app/core/logging_config.py` 增加字段白名单：

```python
    "request_body": (str,),
    "request_body_status": (str,),
    "request_body_truncated": (bool,),
```

增加截断函数：

```python
def _truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True
```

将 `_extra_fields` 改为接收 `max_request_body_bytes`。`request_body` 仅接受字符串，先清除实际换行和控制字符，再调用 `_truncate_utf8`；发生 Formatter 二次截断时强制输出 `request_body_truncated=true`。`request_body_truncated` 是唯一允许的布尔扩展字段，其他字段继续拒绝布尔值。

为 `JsonFormatter`、`TextFormatter` 增加：

```python
max_request_body_bytes: int = 65536
```

并在 `_build_formatter(settings)` 中传入：

```python
max_request_body_bytes=max(1, int(settings.log_request_body_max_bytes))
```

两个 Formatter 调用 `_extra_fields` 时都传递该上限。

- [ ] **Step 6: 运行 Task 1 定向测试**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest tests\test_invoke_request_body_logging.py -q
```

Expected: 本任务已有测试全部 PASS。

- [ ] **Step 7: 提交配置和格式化边界**

临时测试文件不加入暂存区：

```powershell
git add .env.example app/config.py app/core/log_context.py app/core/logging_config.py
git commit -m "feat: add bounded request body log fields"
```

### Task 2: `/invoke` 请求日志事件

**Files:**
- Modify: `app/main.py:9-11,127-166`
- Modify temporarily: `tests/test_invoke_request_body_logging.py`

**Interfaces:**
- Consumes: `settings.log_include_request_body`
- Consumes: `settings.log_request_body_max_bytes`
- Consumes: `_truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]`
- Produces: `_serialize_invoke_request_body(payload: object, max_bytes: int) -> tuple[str | None, bool, str | None]`
- Produces: `_log_invoke_request(request: Request, payload: object, parse_status: str | None) -> None`
- Emits: event `tool.invoke.request`

- [ ] **Step 1: 写 middleware 行为的失败测试**

在临时测试文件继续加入：

```python
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def _request_events(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "tool.invoke.request"
    ]


def test_disabled_does_not_emit_request_body_event(monkeypatch, caplog) -> None:
    monkeypatch.setattr(main_module.settings, "log_include_request_body", False)
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke", lambda *_: {"result": "ok"}
    )
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = TestClient(app).post(
            "/api/v1/tools/dtc_context_service/invoke",
            json={"request_id": "req-1", "arguments": {"brand": "丰田"}},
        )
    assert response.status_code == 200
    assert _request_events(caplog) == []


def test_enabled_emits_complete_invoke_json_but_no_headers(monkeypatch, caplog) -> None:
    monkeypatch.setattr(main_module.settings, "log_include_request_body", True)
    monkeypatch.setattr(main_module.settings, "log_request_body_max_bytes", 65536)
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke", lambda *_: {"result": "ok"}
    )
    request_json = {
        "request_id": "req-1",
        "session_id": "session-1",
        "arguments": {"brand": "丰田", "model": "汉兰达", "year": 2021},
    }
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = TestClient(app).post(
            "/api/v1/tools/dtc_context_service/invoke",
            json=request_json,
            headers={"Authorization": "Bearer secret", "Cookie": "sid=secret"},
        )
    assert response.status_code == 200
    event = _request_events(caplog)[-1]
    assert json.loads(event.request_body) == request_json
    assert event.request_body_truncated is False
    assert "secret" not in event.request_body
    assert not hasattr(event, "authorization")
    assert not hasattr(event, "cookie")


def test_non_invoke_request_never_emits_request_body(monkeypatch, caplog) -> None:
    monkeypatch.setattr(main_module.settings, "log_include_request_body", True)
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert _request_events(caplog) == []


def test_malformed_json_logs_status_without_body(monkeypatch, caplog) -> None:
    monkeypatch.setattr(main_module.settings, "log_include_request_body", True)
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = TestClient(app).post(
            "/api/v1/tools/dtc_context_service/invoke",
            content=b'{"request_id":',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400
    event = _request_events(caplog)[-1]
    assert not hasattr(event, "request_body")
    assert event.request_body_status == "invalid_json"


def test_large_body_is_utf8_safely_truncated_only_in_log(monkeypatch, caplog) -> None:
    monkeypatch.setattr(main_module.settings, "log_include_request_body", True)
    monkeypatch.setattr(main_module.settings, "log_request_body_max_bytes", 40)
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke", lambda *_: {"result": "ok"}
    )
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = TestClient(app).post(
            "/api/v1/tools/dtc_context_service/invoke",
            json={"request_id": "req-large", "arguments": {"text": "丰田" * 100}},
        )
    assert response.status_code == 200
    event = _request_events(caplog)[-1]
    assert len(event.request_body.encode("utf-8")) <= 40
    assert event.request_body_truncated is True
    assert response.json()["echo"] == {"request_id": "req-large"}


def test_serialization_failure_returns_status_without_raising() -> None:
    body, truncated, status = main_module._serialize_invoke_request_body(
        object(), 65536
    )
    assert body is None
    assert truncated is False
    assert status == "serialization_error"
```

- [ ] **Step 2: 运行新增 middleware 测试并确认失败**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest tests\test_invoke_request_body_logging.py -q
```

Expected: Formatter 测试仍 PASS；middleware 事件测试 FAIL，因为事件尚未实现。

- [ ] **Step 3: 实现请求体紧凑序列化**

在 `app/main.py` 导入 `json` 及 `_truncate_utf8`，增加：

```python
def _serialize_invoke_request_body(
    payload: object, max_bytes: int
) -> tuple[str | None, bool, str | None]:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None, False, "serialization_error"
    body, truncated = _truncate_utf8(serialized, max(1, int(max_bytes)))
    return body, truncated, None
```

- [ ] **Step 4: 实现独立请求日志事件**

增加 `_invoke_tool_name` 和 `_log_invoke_request`：

```python
def _invoke_tool_name(path: str) -> str | None:
    parts = path.rstrip("/").split("/")
    return parts[-2] if len(parts) >= 2 and parts[-1] == "invoke" else None


def _log_invoke_request(
    request: Request, payload: object, parse_status: str | None
) -> None:
    log_ctx = current_log_context()
    if parse_status is None:
        body, truncated, status = _serialize_invoke_request_body(
            payload, settings.log_request_body_max_bytes
        )
    else:
        body, truncated, status = None, False, parse_status

    if log_ctx is not None:
        log_ctx.request_body = body
        log_ctx.request_body_truncated = truncated
        log_ctx.request_body_status = status

    fields = {
        "event": "tool.invoke.request",
        "tool_name": _invoke_tool_name(request.url.path),
        "http_method": request.method,
        "http_path": request.url.path,
        "request_body": body,
        "request_body_truncated": truncated,
        "request_body_status": status,
    }
    logger.info(
        "收到工具调用请求",
        extra={key: value for key, value in fields.items() if value is not None},
    )
```

保留 `request_body_truncated=False`，使未截断日志也具有稳定字段。

- [ ] **Step 5: 接入现有 middleware 的 JSON 解析分支**

将 `/invoke` 分支调整为：

```python
        if is_invoke:
            parse_status = None
            try:
                payload = await request.json()
            except (UnicodeDecodeError, ValueError):
                payload = None
                parse_status = "invalid_json"
            request_echo = extract_echo_ids(payload)
            request.state.invoke_echo = request_echo
            echo_ctx.set(request_echo)
            if settings.log_include_request_body:
                _log_invoke_request(request, payload, parse_status)
```

不开启时不做 JSON 二次序列化，也不增加请求事件。请求解析、echo 提取和 `call_next` 的顺序保持原样。

- [ ] **Step 6: 运行请求日志定向测试**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest tests\test_invoke_request_body_logging.py -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 运行接口回归测试**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest tests\test_invoke_echo_request.py tests\test_success_response_envelope.py tests\test_error_response_envelope.py -q
```

Expected: 全部 PASS，响应信封、echo 和错误路径不变。

- [ ] **Step 8: 提交 middleware 实现**

临时测试文件仍不加入暂存区：

```powershell
git add app/main.py
git commit -m "feat: log controlled invoke request bodies"
```

### Task 3: 全量验证与交付清理

**Files:**
- Delete after verification: `tests/test_invoke_request_body_logging.py`
- Verify: `app/config.py`
- Verify: `.env.example`
- Verify: `app/core/log_context.py`
- Verify: `app/core/logging_config.py`
- Verify: `app/main.py`

**Interfaces:**
- Verifies: Agent 响应结构、echo、trace_id 和 RAG 调用行为均未改变。
- Produces: 仅包含生产代码和配置的干净功能分支。

- [ ] **Step 1: 运行全量测试**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest -q
```

Expected: 原有 73 项测试和本功能临时测试全部 PASS；允许保留现有第三方弃用 warning，不允许新增失败。

- [ ] **Step 2: 删除临时测试文件**

使用 `apply_patch` 删除：

```text
tests/test_invoke_request_body_logging.py
```

确认 `git status --short` 中不再出现该文件，并确认两个生产提交都未包含该测试文件。

- [ ] **Step 3: 删除测试后再次运行项目基线**

Run:

```powershell
D:\roxie_management_platform\.venv\Scripts\python.exe -m pytest -q
```

Expected: `73 passed`，仅保留已知第三方弃用 warning。

- [ ] **Step 4: 执行静态和变更范围检查**

Run:

```powershell
git diff main...HEAD --check
git diff main...HEAD -- .env.example app/config.py app/core/log_context.py app/core/logging_config.py app/main.py
git status --short
```

Expected:

- `git diff --check` 无输出；
- 业务改动仅涉及计划中的五个文件；
- 工作树干净；
- 没有 Tool Schema、响应模型、RAG 客户端、服务发现或 Dockerfile 改动。

- [ ] **Step 5: 手工验收两种配置**

关闭配置启动服务后调用 `/invoke`，确认只有既有 `tool.invoke.completed` 摘要。开启：

```dotenv
LOG_INCLUDE_REQUEST_BODY=true
LOG_REQUEST_BODY_MAX_BYTES=65536
```

再次调用，确认新增 `tool.invoke.request`，其 `request_body` 包含 Agent 提交的顶层 ID 和 `arguments`，响应仍为原有 `{code,message,data,trace_id,echo}`。

- [ ] **Step 6: 准备评审信息**

记录分支名、两个生产提交号、`73 passed` 结果以及启用配置。未经用户再次确认，不推送、不合并 `main`、不更新 SVN 部署包。
