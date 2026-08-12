# Tool 中台第一批日志管理优化设计方案

## 1. 文档信息

- 项目：`roxie-router-service`
- 技术方案：方案 A，Python 标准库 `logging`
- 实施批次：第一批——核心日志安全
- Python：3.13
- 基线：当前 `main`，现有测试基线 `45 passed`
- 设计日期：2026-08-12

## 2. 改造目标

本批次只优化 Tool 中台内部日志，不修改 Agent、Tool 或 RAG 的业务协议。

目标如下：

1. 删除完整 Tool 请求参数和完整返回结果日志。
2. 生产环境支持单行 JSON 日志，开发环境支持文本日志。
3. 统一日志配置，取消 `dictConfig` 与手工 handler 混用。
4. 每条应用日志自动关联当前请求的 `trace_id`。
5. 一次成功的 Tool invoke 默认只保留一条完成摘要日志。
6. 400、404 等预期错误不打印堆栈。
7. 未知程序异常只打印一次服务端堆栈。
8. 日志只输出 stdout/stderr，不写容器内日志文件。
9. 日志改造不能改变接口响应内容和 RAG 请求内容。

## 3. 本批次不做的内容

以下内容不属于第一批范围：

- Tool 接口异步化；
- `httpx.AsyncClient` 与连接池重构；
- Nacos 实例缓存；
- Nacos 持续故障日志限频；
- `discovery_ms`、`upstream_ms` 的精细计时；
- 并发隔离、Semaphore 和背压；
- Prometheus、OpenTelemetry 或其他指标系统；
- request/session ID 的 HMAC 摘要；
- Tool Schema、槽位提取或 RAG 接口调整；
- 错误码和 HTTP 状态码调整。

这些内容留到后续批次，避免本次日志改造扩大为调用链重构。

## 4. 接口兼容性约束

以下行为必须保持不变：

```text
GET  /api/v1/tools
GET  /api/v1/tools/{tool_name}
POST /api/v1/tools/{tool_name}/invoke
POST /api/v1/diagnoses
POST /api/v1/dtc-cause-cards
GET  /api/v1/health
```

不得改变：

- 请求体 `arguments` 的格式；
- 顶层 `id` / `*_id` 提取规则；
- `echo` 回显规则；
- `code`、`message`、`data`、`trace_id`、`echo` 响应结构；
- 8 个 Tool 名称；
- Tool input/output Schema；
- 槽位提取和未知字段过滤；
- RAG 请求参数、路径和超时；
- 当前业务错误码及 HTTP 状态码。

本次唯一可见变化是服务端 stdout 日志的格式和内容。

## 5. 当前问题

一次成功的 `/invoke` 当前可能产生以下日志：

```text
收到工具调用请求
invoke_tool arguments=完整请求参数
转发工具调用 URL
invoke_tool result=完整业务结果
```

主要风险：

- 车辆、故障码、Agent 元数据和维修内容被完整写入日志；
- 后续若请求包含 VIN、Token 或用户数据，会形成敏感信息泄露；
- 大响应转字符串并写 stdout，增加 CPU 和 I/O；
- 一次成功调用分散成多条日志，不便于检索和统计；
- 当前 `dictConfig` 和 `get_app_logger()` 手工 handler 混用；
- 业务日志不能自动携带 `trace_id`；
- Tool handler 异常和全局异常可能重复打印堆栈。

## 6. 总体设计

```text
HTTP 请求
   │
   ▼
trace/log middleware
   ├─ 获取或生成 trace_id
   ├─ 创建请求级日志上下文
   ├─ 记录开始时间
   │
   ▼
原有 Tool 调用链
   │  不记录请求和响应正文
   ▼
HTTP 响应 / 异常响应
   │
   ▼
middleware 输出一条请求完成摘要日志
   │
   ▼
清理 ContextVar
```

日志上下文只保存摘要字段，不保存请求体、返回值或请求 Header。

## 7. 日志配置

### 7.1 新增配置

在 `app/config.py` 增加：

```python
log_level: str = "INFO"
log_format: str = "json"
access_log_enabled: bool = False
log_include_caller: bool = False
log_message_max_length: int = 1024
```

在 `.env.example` 增加：

```dotenv
# json：生产环境；text：本地开发
LOG_FORMAT=json
LOG_LEVEL=INFO
ACCESS_LOG_ENABLED=false
LOG_INCLUDE_CALLER=false
LOG_MESSAGE_MAX_LENGTH=1024
```

不提供以下配置：

```text
LOG_REQUEST_BODY
LOG_RESPONSE_BODY
LOG_HEADERS
```

避免生产环境误开启完整正文日志。

### 7.2 默认行为

生产环境推荐：

```dotenv
LOG_FORMAT=json
LOG_LEVEL=INFO
ACCESS_LOG_ENABLED=false
```

本地开发可使用：

```dotenv
LOG_FORMAT=text
LOG_LEVEL=DEBUG
ACCESS_LOG_ENABLED=true
```

## 8. JSON 日志格式

### 8.1 公共字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `timestamp` | string | ISO 8601 时间，包含时区 |
| `level` | string | 日志级别 |
| `service` | string | `roxie-router-service` |
| `version` | string | 应用版本 |
| `logger` | string | logger 名称 |
| `event` | string | 稳定事件名 |
| `trace_id` | string/null | 当前请求链路 ID |

### 8.2 Tool 完成日志字段

| 字段 | 说明 |
|---|---|
| `tool_name` | Tool 名称 |
| `status` | `success`、`validation_error`、`tool_not_found`、`internal_error` 等 |
| `http_method` | HTTP 方法 |
| `http_path` | 不包含查询参数的路径 |
| `http_status` | HTTP 状态码 |
| `business_code` | 中台业务码 |
| `duration_ms` | 中台请求总耗时 |
| `request_bytes` | 请求体字节数，无法安全获取时省略 |
| `response_bytes` | 响应字节数，无法安全获取时省略 |
| `dtc_count` | DTC 数量，只记录数量 |
| `error_type` | 异常类型，不记录原始异常正文 |

本批次不记录 `discovery_ms` 和 `upstream_ms`，避免修改 RAG 与 Nacos 调用层。后续批次再补充。

### 8.3 成功日志示例

```json
{
  "timestamp": "2026-08-12T11:05:10.328+08:00",
  "level": "INFO",
  "service": "roxie-router-service",
  "version": "0.1.0",
  "logger": "app.main",
  "event": "tool.invoke.completed",
  "trace_id": "c76a8e13a3d34e42",
  "tool_name": "dtc_grouping_service",
  "status": "success",
  "http_method": "POST",
  "http_path": "/api/v1/tools/dtc_grouping_service/invoke",
  "http_status": 200,
  "business_code": 0,
  "duration_ms": 232.4,
  "request_bytes": 358,
  "response_bytes": 4186,
  "dtc_count": 4
}
```

## 9. 日志安全规则

### 9.1 字段白名单

结构化 Formatter 只允许明确声明的扩展字段，不直接序列化 `LogRecord.__dict__`。

允许字段：

```text
event
trace_id
tool_name
status
http_method
http_path
http_status
business_code
duration_ms
request_bytes
response_bytes
dtc_count
error_type
```

### 9.2 禁止记录

```text
arguments
result
request_body
response_body
Authorization
Cookie
Token
Password
Secret
Nacos 密码
VIN 原文
request_id 原文
session_id 原文
tenant_id 原文
车辆维修完整内容
```

Agent 的业务 ID 仍正常返回到响应 `echo`，只是不会进入日志。

### 9.3 message 安全处理

普通日志 message 需要：

- 删除或替换换行、回车和控制字符；
- 限制最大长度，默认 1024；
- 避免格式化字典、Pydantic 模型和请求对象；
- 不包含上游响应正文；
- 不包含 Authorization、Token、Password 等内容。

## 10. trace_id 处理

现有 `trace_id_ctx` 继续作为唯一请求级 trace 来源。

本批次日志层自动读取 `trace_id_ctx`，不改变响应中的 `trace_id` 生成和透传规则。

为避免改变 Agent 接口行为，第一批不调整 `X-Trace-Id` 的合法性规则。trace ID 长度和字符安全限制
归入后续“请求安全边界”改造，不和日志重构混在一起。

## 11. 请求级日志上下文

新增 `app/core/log_context.py`：

```python
@dataclass
class RequestLogContext:
    tool_name: str | None = None
    business_code: int | None = None
    status: str = "success"
    dtc_count: int | None = None
    error_type: str | None = None
```

并定义：

```python
request_log_ctx: ContextVar[RequestLogContext | None]
```

上下文生命周期：

1. middleware 为请求创建上下文；
2. invoke endpoint 设置 `tool_name` 和 `dtc_count`；
3. 异常处理器设置 `business_code`、`status` 和 `error_type`；
4. middleware 输出完成日志；
5. middleware 使用 token 恢复 ContextVar。

上下文不能保存原始 `arguments`、RAG 返回对象或 echo ID。

## 12. 日志格式化器

### 12.1 `JsonFormatter`

使用标准库 `json.dumps()` 输出单行 JSON。

要求：

- `ensure_ascii=False`，中文保持可读；
- `default=str` 不用于任意业务对象；
- 只输出公共字段和白名单扩展字段；
- 异常堆栈单独处理；
- 不记录局部变量；
- 每条日志末尾只保留一个换行符。

### 12.2 `TextFormatter`

本地文本格式示例：

```text
2026-08-12 11:05:10 INFO trace=c76a8e13 tool=dtc_grouping_service event=tool.invoke.completed status=success duration_ms=232.4
```

JSON 和 text 使用相同事件与字段，只改变展示形式。

### 12.3 `ContextFilter`

自动为日志注入：

```text
service
version
trace_id
```

没有 HTTP 请求上下文的启动日志和 Nacos 后台日志，`trace_id` 为 `null`。

## 13. 日志事件与级别

| 场景 | event | 级别 | 堆栈 |
|---|---|---:|---:|
| Tool 成功 | `tool.invoke.completed` | INFO | 否 |
| 入参错误 | `tool.invoke.completed` | WARNING | 否 |
| Tool 不存在 | `tool.invoke.completed` | WARNING | 否 |
| 上游可预期错误 | `tool.invoke.completed` | ERROR | 否 |
| 未知程序异常 | `application.unhandled_error` | ERROR | 是，一次 |
| 非 invoke 请求完成 | `http.request.completed` | INFO | 否 |
| 契约加载完成 | `tool.contracts.loaded` | INFO | 否 |
| 服务启动/关闭 | `service.started/stopping` | INFO | 否 |

未知异常可以产生：

1. 一条 `application.unhandled_error` 安全堆栈；
2. 一条不带堆栈的请求完成摘要。

其他预期错误只产生完成摘要，不打印 Python 堆栈。

## 14. 单次 Tool 调用日志规则

成功调用删除以下现有日志：

```python
logger.info("收到工具调用请求: %s", request.url.path)
logger.info("invoke_tool: tool_name=%s, arguments=%s", ...)
logger.info("转发工具调用: %s -> POST %s", ...)
logger.info("invoke_tool: tool_name=%s, result=%s", ...)
```

替换为 middleware 结束时的一条：

```text
tool.invoke.completed
```

第一批允许保留 Nacos 生命周期必要日志，但统一经过同一个 Formatter。Nacos 限频和状态聚合放到
第二批实施。

## 15. 异常日志归属

| 异常来源 | 日志处理 |
|---|---|
| 请求模型校验 | 完成摘要 WARNING，不打印堆栈 |
| Tool input schema 校验 | 完成摘要 WARNING，不打印堆栈 |
| Tool 不存在 | 完成摘要 WARNING，不打印堆栈 |
| RAG 业务错误 | 完成摘要 ERROR，不打印 Python 堆栈 |
| RAG 超时/连接失败 | 完成摘要 ERROR，只记录异常类型 |
| Tool handler 未知异常 | 不在 registry 重复打印，由全局异常层记录一次 |
| FastAPI 未处理异常 | 全局异常处理器记录一次安全堆栈 |
| Nacos 后台异常 | Nacos 生命周期模块记录，因为没有 HTTP 请求完成日志 |

客户端响应文案和错误码在本批次保持不变。内部异常防泄露是另一项 P0 工作，需单独设计和实施。

## 16. 文件修改清单

### `app/config.py`

新增日志配置字段，不修改现有 Tool、RAG 和 Nacos 配置语义。

### `.env.example`

增加 JSON/text、日志级别和 access log 示例。

### `app/core/logging_config.py`

主要改造内容：

- 新增 `JsonFormatter`；
- 新增统一 `TextFormatter`；
- 新增 `ContextFilter`；
- 新增 `configure_logging(settings)`；
- 统一 root、app、uvicorn 和第三方 logger；
- 删除 `get_app_logger()` 手工挂 handler 的逻辑；
- `get_app_logger()` 只返回 `logging.getLogger(name)`；
- 重复调用配置函数不能重复添加 handler。

### `app/core/log_context.py`

新增请求级摘要上下文，不存放业务正文。

### `app/main.py`

- 统一初始化日志；
- middleware 计算总耗时；
- middleware 输出请求完成事件；
- 请求结束清理日志 ContextVar；
- 删除“收到工具调用请求”日志；
- 异常处理器更新日志上下文；
- 未知异常只在全局异常层记录一次。

### `app/api/v1/endpoints/tools.py`

- 删除完整 `arguments` 日志；
- 删除完整 `result` 日志；
- 设置 `tool_name`；
- 只从已解析参数计算 `dtc_count`，不保存 DTC 内容。

### `app/core/registry.py`

删除或降级 handler 未知异常的重复堆栈日志，异常仍按原逻辑包装成 `ToolExecutionError`。

### `app/services/rag_client.py`

删除成功转发 INFO 日志。第一批不改变请求实现、URL 选择、超时和错误映射。

### `Dockerfile`

保持容器 stdout/stderr 模式。是否关闭 Uvicorn access log由 `ACCESS_LOG_ENABLED` 控制，不在容器内
创建业务日志文件。

## 17. 性能约束

第一批每个请求新增的工作仅包括：

- `perf_counter()` 开始与结束计时；
- 少量 `ContextVar` 读写；
- 构造小型字段字典；
- 一次小型 `json.dumps()`；
- 一次 stdout 写入。

禁止：

- 递归扫描请求或响应做脱敏；
- 同步写磁盘日志；
- 请求中调用远程日志服务；
- 对请求/响应计算 Hash；
- 读取 StreamingResponse/SSE 正文；
- 为计算日志大小重复序列化大型业务对象。

由于删除了完整请求、完整响应和多条重复日志，预计整体日志开销下降。

## 18. 测试与验证策略

### 18.1 开发期间临时测试

开发期间先新增临时测试，验证：

- JSON 日志每行可解析；
- text 日志可读；
- `LOG_LEVEL` 生效；
- handler 不重复挂载；
- 自动注入 `trace_id`；
- 并发请求不会串 trace；
- 成功 Tool 调用只有一条完成事件；
- 日志中不出现完整 arguments 和返回结果；
- 日志中不出现 request/session/tenant ID 原文；
- 400/404 不打印堆栈；
- 未知 500 只打印一次堆栈；
- Tool 接口响应结构不变。

### 18.2 测试文件处理约定

根据本次要求：

1. 现有 45 项测试全部保留，不删除；
2. 本次新增日志测试在开发和验收阶段使用；
3. 完整测试和人工验收通过后，删除本次新增的临时日志测试文件；
4. 删除测试后再次执行现有 45 项测试；
5. 只提交业务实现、配置和文档，不提交本次临时日志测试文件。

风险说明：删除新增测试后，代码库将失去日志脱敏、单条完成日志、trace 并发隔离和异常去重的
自动回归保护。未来再次修改日志模块时，需要重新建立这些测试。更稳妥的工程做法是保留测试，
但本方案按当前要求执行删除。

### 18.3 现有回归测试

必须继续通过：

```text
45 passed
```

重点关注：

```text
tests/test_invoke_echo_request.py
tests/test_success_response_envelope.py
tests/test_error_response_envelope.py
tests/test_rag_client.py
tests/test_orchestrator_examples.py
```

## 19. 验收标准

### 接口兼容性

- Agent 请求和响应结构无变化；
- `echo` 和 `trace_id` 行为无变化；
- RAG 请求参数和路径无变化；
- 业务错误码和 HTTP 状态码无变化；
- 现有 45 项测试全部通过。

### 日志安全

- 不记录完整 `arguments`；
- 不记录完整 RAG/Tool 结果；
- 不记录 echo ID 原文；
- 不记录 Header、Token、Password、Secret；
- message 不允许换行注入且有长度限制。

### 日志行为

- `LOG_FORMAT=json` 输出合法单行 JSON；
- `LOG_FORMAT=text` 输出统一文本；
- Tool 成功调用默认一条完成日志；
- 所有应用日志自动关联可用的 `trace_id`；
- 预期错误不打印堆栈；
- 未知异常只记录一次堆栈；
- 容器不创建业务日志文件。

### 性能

- 日志大小不随 RAG 响应正文大小线性增长；
- 不为日志重复读取或序列化完整响应；
- 相同 mock RAG 场景下不应出现明显响应耗时回退。

## 20. 实施顺序

```text
1. 补临时失败测试，锁定接口与日志要求
2. 增加日志配置和请求日志上下文
3. 实现 JSON/text Formatter 和统一配置
4. 中间件输出请求完成摘要
5. 删除完整请求、结果和重复成功日志
6. 统一预期错误与未知异常日志归属
7. 运行临时日志测试和现有 45 项测试
8. 人工检查 JSON/text 日志示例
9. 删除本次新增临时日志测试
10. 再次运行现有 45 项测试
11. 提交业务代码、配置和设计文档
```

## 21. 回滚方案

本批次不修改数据库、Tool 契约或外部协议。若上线后日志采集不兼容，可：

1. 临时设置 `LOG_FORMAT=text`，无需回滚业务代码；
2. 如仍有问题，回滚本批次 Git 提交；
3. Agent、Tool 和 RAG 无需同步回滚；
4. 容器部署继续通过 stdout/stderr 输出日志。

## 22. 后续批次

第一批稳定后，再单独评审第二批：

- Nacos 注册/发现日志状态变化与限频；
- `discovery_ms` 和 `upstream_ms`；
- AsyncClient 与连接池指标；
- QPS、错误率、p95/p99 和当前并发；
- 云日志平台字段映射；
- trace ID 安全边界；
- request/session ID 的可选 HMAC 摘要。
