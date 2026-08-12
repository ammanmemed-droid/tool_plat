# Roxie Tool 中台核心代码阅读指南

本文面向第一次接触 `roxie-router-service` 的后端开发人员，目标不是逐行解释仓库里的所有
历史文件，而是帮助你快速建立运行时心智模型，并能独立完成 Tool 接口联调、契约调整和故障排查。

## 1. 先建立一个最小心智模型

这个项目不是 Repair Agent，也不负责保存维修会话。它是 Agent 与 RAG 之间的 Tool 网关：

```text
Agent / 编排层
    │
    │ POST /api/v1/tools/{tool_name}/invoke
    ▼
FastAPI 接口层
    │ 解析请求、提取 trace_id 与顶层 ID
    ▼
ToolRegistry
    │ 槽位提取 → 入参校验 → 执行 handler → 出参校验
    ▼
Tool handler
    │ 7 个远程代理                     1 个本地工具
    ├────────────────────────────┐      └─ maintenance_light_reset_service
    ▼                            │
RagServiceClient                 │
    │ Nacos 实时发现或 RAG_BASE_URL 直连
    ▼
roxie-supper-rag-service
```

理解项目时要一直记住四个边界：

1. `myskills/*/tool-schema.json` 是 Tool 输入和输出契约的唯一来源。
2. `app/tools/*.py` 是工具 handler；大多数文件只负责把工具名映射到 RAG 路径。
3. `app/core/registry.py` 是所有 Tool 调用共同经过的核心流水线。
4. `/api/v1/diagnoses` 和 `/api/v1/dtc-cause-cards` 是兼容旧调用方的原生代理端点，和
   `/tools/{tool_name}/invoke` 不是同一套响应语义。

## 2. 推荐阅读顺序

### 2.1 30 分钟快速路线

按下面的顺序阅读，可以最快串起主链路：

| 顺序 | 文件 | 重点阅读位置 | 预计时间 |
|---|---|---|---:|
| 1 | [`README.md`](../README.md) | 架构、8 个 Tool、启动与测试命令 | 3 分钟 |
| 2 | [`app/main.py`](../app/main.py) | `lifespan`、`trace_id_middleware`、异常处理器 | 5 分钟 |
| 3 | [`app/api/v1/endpoints/tools.py`](../app/api/v1/endpoints/tools.py) | `invoke_tool()` 如何进入注册中心 | 2 分钟 |
| 4 | [`app/api/v1/schemas.py`](../app/api/v1/schemas.py) | `ToolInvokeRequest`、扁平请求兼容、`ToolInvokeResponse` | 4 分钟 |
| 5 | [`app/core/registry.py`](../app/core/registry.py) | `load_contracts()` 和 `invoke()` | 5 分钟 |
| 6 | [`app/core/slot_extractor.py`](../app/core/slot_extractor.py) | `extract_slots()`、路径展开、数组去重 | 4 分钟 |
| 7 | [`app/services/rag_client.py`](../app/services/rag_client.py) | URL 选择、trace 透传、错误映射、响应解包 | 4 分钟 |
| 8 | [`app/tools/dtc_context.py`](../app/tools/dtc_context.py) | 一个典型远程代理 handler | 1 分钟 |
| 9 | [`myskills/dtc-context-skill/tool-schema.json`](../myskills/dtc-context-skill/tool-schema.json) | `input_schema`、`x-extract`、`output_schema` | 2 分钟 |

### 2.2 第二遍阅读

第一遍理解主链路后，再看以下内容：

- Nacos 注册：[`app/core/nacos.py`](../app/core/nacos.py)
- RAG 实例发现：[`app/core/discovery.py`](../app/core/discovery.py)
- JSON Schema 校验及 `null` 处理：[`app/core/validation.py`](../app/core/validation.py)
- Agent ID 回显测试：[`tests/test_invoke_echo_request.py`](../tests/test_invoke_echo_request.py)
- 五工具联调示例：[`examples/orchestrator/README.md`](../examples/orchestrator/README.md)

不建议一开始阅读 `app/tools/knowledge.py`。它主要是本地演示知识数据，目前只有保养归零工具
直接使用其中的保养 SOP；它不是五个 RAG Tool 的数据来源。

## 3. 服务启动流程

入口是 [`app/main.py`](../app/main.py)。启动时依次发生以下动作：

1. `import app.tools` 导入 [`app/tools/__init__.py`](../app/tools/__init__.py)。
2. `app/tools/__init__.py` 导入 8 个工具模块。
3. 每个工具模块的 `@register_tool("...")` 在导入阶段向全局 `tool_registry` 注册 handler。
4. FastAPI `lifespan()` 调用 `tool_registry.load_contracts(settings.skills_dir)`。
5. 注册中心扫描 `myskills/*/tool-schema.json`，按 `tool_name` 把契约绑定到 handler。
6. `NacosRegistrar.register()` 在后台注册本中台服务，不可达时不阻断 FastAPI 启动。
7. `RagServiceDiscovery` 复用同一个 Nacos naming service，为调用 RAG 做实时实例发现。

可以把注册过程理解为两次绑定：

```text
代码导入阶段：tool_name → Python handler
启动阶段：    tool_name → input_schema + output_schema + Skill 元数据
```

如果新增了 `tool-schema.json` 却没有导入对应 Python 模块，日志会提示“契约无对应已注册 handler”；
反过来只有 handler 没有契约，则会提示“工具缺少契约文件”。

## 4. `/invoke` 完整调用链

以请求为例：

```json
{
  "request_id": "req-001",
  "session_id": "session-001",
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137"]
  }
}
```

### 4.1 请求级上下文

[`app/main.py`](../app/main.py) 中的 `trace_id_middleware()` 最先处理请求：

- 优先读取 `X-Trace-Id`，未传则生成 UUID；
- 只对 `POST .../invoke` 读取请求体并提取顶层 ID；
- 把 `trace_id` 和 `echo` 放入 `ContextVar`，保证并发请求互不污染；
- 响应头始终写入 `X-Trace-Id`；
- 请求结束后用 token 恢复上下文。

`ContextVar` 很重要，因为成功响应由 Pydantic 模型生成，错误响应由全局异常处理器生成，
两条路径都需要访问同一份请求级 `trace_id` 和 `echo`。

### 4.2 请求模型解析

[`app/api/v1/schemas.py`](../app/api/v1/schemas.py) 的 `ToolInvokeRequest` 支持两种写法：

推荐格式：

```json
{
  "request_id": "req-001",
  "arguments": {"brand": "丰田", "model": "汉兰达", "dtc_codes": ["P0136"]}
}
```

兼容的扁平格式：

```json
{
  "request_id": "req-001",
  "brand": "丰田",
  "model": "汉兰达",
  "dtc_codes": ["P0136"]
}
```

`merge_flat_payload()` 的关键规则：

- `arguments` 是非空对象时，以它为准，其他顶层业务字段不会合并进去；
- `arguments` 缺失或为空时，非 ID 顶层字段被收进 `arguments`；
- ID 字段不会进入 `arguments`；
- 顶层 ID 只接受字符串、整数或 `null`，布尔、数组、对象会触发 `40000`；
- `extra="allow"` 是为了允许 Agent 携带动态的顶层 ID。

### 4.3 API 入口

[`app/api/v1/endpoints/tools.py`](../app/api/v1/endpoints/tools.py) 的 `invoke_tool()` 很薄：

```text
request.arguments
      ↓
tool_registry.invoke(tool_name, arguments)
      ↓
ToolInvokeResponse(data=result)
```

这里不写业务逻辑，所有工具共同行为集中在注册中心，避免不同 Tool 出现不同校验规则。

### 4.4 注册中心流水线

[`app/core/registry.py`](../app/core/registry.py) 的 `ToolRegistry.invoke()` 是项目最重要的函数：

```text
1. get_tool(tool_name)                 不存在 → 40400
2. extract_slots(arguments, schema)    白名单投影、嵌套路径提取
3. normalize_arguments(...)            工具专属兼容归一化（当前无已注册规则）
4. validate input_schema               不通过 → 40000
5. tool.handler(arguments)             普通异常 → 50002
6. strip_invalid_nulls(result, schema) 清理契约不允许的 null
7. validate output_schema              不通过 → 50001
8. return result
```

需要特别注意顺序：槽位提取在 Schema 校验之前。Agent 可以发“大请求”，但进入 handler 和 RAG
的只有当前 Tool 声明的业务字段。

## 5. Agent ID 提取与 `echo` 回显

核心代码位于 [`app/core/responses.py`](../app/core/responses.py) 和
[`app/main.py`](../app/main.py)。

### 5.1 匹配规则

`is_echo_id_key()` 只匹配：

- 字段名恰好等于 `id`；
- 字段名以 `_id` 结尾。

例如：

| 字段 | 是否回显 | 原因 |
|---|---:|---|
| `id` | 是 | 精确匹配 |
| `request_id` | 是 | `_id` 后缀 |
| `session_id` | 是 | `_id` 后缀 |
| `tenant_id` | 是 | `_id` 后缀 |
| `task_id` | 是 | `_id` 后缀，整数也允许 |
| `requestId` | 否 | 大小写敏感，不是 `_id` 后缀 |
| `identity` | 否 | 不是 `_id` 后缀 |
| `arguments.reason_id` | 否 | 只扫描请求体顶层，不递归 |

值为 `null` 的 ID 不进入 `echo`。Python 中 `bool` 是 `int` 的子类，因此代码显式排除了布尔值。

### 5.2 成功与错误路径

成功响应由 `ToolInvokeResponse.echo` 的默认工厂从 `echo_ctx` 获取：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "trace_id": "trace-001",
  "echo": {"request_id": "req-001", "session_id": "session-001"}
}
```

错误路径通过 `app/main.py::_error_content()` 手动补上 `echo`。因此入参校验错误、上游超时、
工具执行异常和未处理异常都会使用相同回显规则。没有匹配 ID 时仍返回 `"echo": {}`。

请求体里的顶层 `trace_id` 只是普通的 echo ID，不会覆盖响应信封的 `trace_id`；真正的链路 ID
来自 `X-Trace-Id` 请求头。

## 6. 槽位提取与白名单过滤

核心文件是 [`app/core/slot_extractor.py`](../app/core/slot_extractor.py)。

### 6.1 两种过滤模式

1. Schema 有 `x-extract`：按字段对应的候选路径依次提取，第一个有效路径获胜。
2. Schema 没有 `x-extract`：按 `properties` 做顶层白名单投影。

因此 8 个 Tool 都会丢弃 Schema 未声明的 Agent 字段，不会把整个胖请求发给 RAG 或本地工具。

### 6.2 `x-extract` 如何工作

五个 RAG Tool 的契约中有类似声明：

```json
{
  "x-extract": {
    "brand": ["brand", "vehicle_info.brand"],
    "model": ["vehicle_info.model", "model"],
    "year": ["year", "vehicle_info.year"],
    "dtc_codes": [
      "dtc_codes",
      "system_dtc_groups[].dtc_codes[].dtc_code"
    ]
  }
}
```

关键实现：

- `_values_at_path()` 解析点分路径；`[]` 表示展开数组；
- `_flatten()` 递归摊平嵌套数组；
- `_normalize_scalar()` 去除字符串首尾空白，并把纯数字年份转为整数；
- `_normalize_array()` 去空值、去重，并把 `dtc_codes` 转成大写；
- `extract_slots()` 对每个目标字段依次尝试候选路径。

它不是通用 JSONPath 实现，只支持“点分字段 + `[]` 数组展开”。新增路径时应先在
`tests/test_registry_slot_extraction.py` 或 `tests/test_five_tool_contracts.py` 增加用例。

## 7. Schema 校验与 `null` 规范化

[`app/core/validation.py`](../app/core/validation.py) 负责输入、输出契约校验。

### 7.1 输入校验

`validate_against_schema()` 使用 JSON Schema 自身声明的 draft，最多汇总前 5 个错误，并显示
字段路径。输入不满足契约时抛出 `ToolInputValidationError`，业务码为 `40000`。

### 7.2 输出校验

RAG 返回后，中台同样用 `output_schema` 校验。这样可以在中台边界发现 RAG 契约漂移，而不是把
错误结构继续交给 Agent。输出不匹配时业务码为 `50001`。

### 7.3 为什么先清理 `null`

部分远端响应会为未填充的可选字段返回显式 `null`，但 Schema 可能把该字段定义成可选的
`string`，而不是 `string | null`。`strip_invalid_nulls()` 会：

- 保留 Schema 明确允许的 `null`；
- 删除 Schema 不允许的 `null`，把它视作“字段缺省”；
- 递归处理对象和数组；
- 解析契约内 `#/...` 本地 `$ref`。

这一步只发生在输出侧，不会替 Agent 修复输入错误。

## 8. RAG 转发、服务发现与错误处理

### 8.1 Tool handler

五个强类型工具 handler 几乎没有业务逻辑，它们只完成工具名、RAG 路径和超时的映射：

| Tool | Python 文件 | RAG 接口 | 超时配置 |
|---|---|---|---|
| `dtc_context_service` | `app/tools/dtc_context.py` | `/api/v1/tool-services/dtc-context` | `RAG_TIMEOUT`，默认 15s |
| `dtc_grouping_service` | `app/tools/dtc_grouping.py` | `/api/v1/tool-services/dtc-grouping` | `RAG_TIMEOUT`，默认 15s |
| `cause_ranking_service` | `app/tools/cause_ranking.py` | `/api/v1/tool-services/cause-ranking` | `CAUSE_RANKING_TIMEOUT`，默认 50s |
| `diagnostic_planning_service` | `app/tools/diagnostic_planning.py` | `/api/v1/tool-services/diagnostic-planning` | `RAG_TIMEOUT`，默认 15s |
| `repair_planning_service` | `app/tools/repair_planning.py` | `/api/v1/tool-services/repair-planning` | `RAG_TIMEOUT`，默认 15s |
| `diagnose_service` | `app/tools/diagnose.py` | `/api/v1/diagnoses` | `DIAGNOSE_TIMEOUT`，默认 60s |
| `dtc_cause_cards_service` | `app/tools/dtc_cause_cards.py` | `/api/v1/dtc-cause-cards` | `DIAGNOSE_TIMEOUT`，默认 60s |

### 8.2 URL 选择

[`app/services/rag_client.py`](../app/services/rag_client.py) 的 `_candidate_urls()`：

1. 配置 `RAG_BASE_URL` 时直接使用该地址，跳过 Nacos；
2. 否则调用 `rag_discovery.pick_instance()` 实时查询健康实例；
3. 没有实例时抛出工具执行错误。

[`app/core/discovery.py`](../app/core/discovery.py) 不缓存 RAG 实例。每次调用都通过
`asyncio.run_coroutine_threadsafe()` 把 Nacos 查询提交给 FastAPI 主事件循环，然后随机选择一个
健康、启用的实例。同步 Tool endpoint 会在线程池执行，因此这段同步到异步的桥接是必要的。

### 8.3 HTTP 调用

`RagServiceClient.invoke()` 会：

- 把当前 `trace_id_ctx` 作为 `X-Trace-ID` 发给 RAG；
- 使用工具对应的超时；
- 接受 RAG 裸业务对象；
- 也接受 `{code, message, data}` 信封，`code=0` 时只取 `data`；
- RAG 信封 `code != 0` 时转成 `50002` 工具执行错误；
- 非 JSON 或非对象响应转成 `50002`。

### 8.4 错误码

| 业务码 | HTTP 状态 | 含义 |
|---:|---:|---|
| `40000` | 400 | 请求模型或 Tool `input_schema` 校验失败 |
| `40400` | 404 | Tool 不存在 |
| `50000` | 500 | 未处理的中台内部异常 |
| `50001` | 500 | Tool 输出不符合 `output_schema` |
| `50002` | 500 | Tool/RAG 执行失败 |
| `50200` | 502 | RAG 返回 HTTP 502 |
| `50300` | 503 | RAG 返回 HTTP 503 |
| `50400` | 504 | RAG 返回 HTTP 504，或中台调用 RAG 超时 |

## 9. Nacos 的两个不同职责

不要混淆 [`app/core/nacos.py`](../app/core/nacos.py) 和
[`app/core/discovery.py`](../app/core/discovery.py)：

| 文件 | 职责 | 被谁使用 |
|---|---|---|
| `nacos.py` | 把本中台注册为 `roxie-router-service`，使 Agent 能发现中台 | FastAPI `lifespan` |
| `discovery.py` | 发现 `roxie-supper-rag-service`，使中台能调用 RAG | `RagServiceClient` |

`NacosRegistrar` 的重点逻辑：

- `detect_local_ip()` 探测注册 IP；
- `build_client_config()` 设置 namespace、鉴权、gRPC 端口偏移和心跳；
- `register()` 启动后台生命周期任务，不阻塞服务启动；
- `_async_main()` 首次失败后持续重试；
- `_create_and_register()` 创建 naming service 并注册临时实例；
- `deregister()` 在服务关闭时注销并关闭 SDK。

`_patch_sdk_async_close()` 是针对当前 Nacos SDK 异步关闭行为的兼容补丁。升级 SDK 时应重点回归，
确认补丁是否仍需要。

## 10. 8 个 Tool 应该怎么看

### 10.1 五个 RAG 0.8.0 强类型 Tool

五个 Tool 使用相同公共输入：

```text
brand + model + dtc_codes
可选：year + language
```

它们的业务差异主要在 RAG 和各自 `output_schema`，中台 handler 本身没有原因排序、诊断规划或
维修规划算法。阅读时不要在 `app/tools/*.py` 中寻找这些算法，应重点看对应
`myskills/*/tool-schema.json` 和 RAG 文档。

推荐业务顺序：

```text
dtc_context_service（完整 DTC）
    ↓
dtc_grouping_service（完整 DTC）
    ↓ 选择一个 groups[].dtc_codes
    ├─ cause_ranking_service
    ├─ diagnostic_planning_service
    └─ repair_planning_service
```

完整请求和响应见 [`examples/orchestrator/README.md`](../examples/orchestrator/README.md)。

### 10.2 `diagnose_service` 与 `dtc_cause_cards_service`

这两个也是 `/invoke` Tool，因此仍经过槽位过滤、输入校验、输出校验和统一响应信封；但它们有
独立契约和 60 秒超时，路径前缀是 `/api/v1`，不是 `/api/v1/tool-services`。

同时 [`app/api/v1/endpoints/rag_proxy.py`](../app/api/v1/endpoints/rag_proxy.py) 还暴露了同名
原生 REST 代理：

```text
POST /api/v1/diagnoses
POST /api/v1/dtc-cause-cards
```

原生代理请求和响应都尽量保持 RAG 原接口形态，不走 Tool Schema，也不包装中台信封。新 Agent
接入应优先使用 `/tools/{tool_name}/invoke`；旧调用方需要零改造透传时才使用原生代理。

### 10.3 `maintenance_light_reset_service`

这是唯一的本地工具，核心在
[`app/tools/maintenance_light_reset.py`](../app/tools/maintenance_light_reset.py)：

- `guide`：按品牌、车型、年款匹配 SOP；匹配不到时降级到相近年款或通用路径，并明确不确定性；
- `execute`：依次检查车辆信息、设备连接、设备能力和用户确认；
- 用户明确取消时返回 `cancelled`；
- 未确认时返回 `awaiting_confirmation`；
- 当前真正的设备执行尚未接入，最后的 `success` 是模拟返回。

本地数据位于 [`app/tools/knowledge.py`](../app/tools/knowledge.py)。目前维护时重点看
`MAINTENANCE_SOP_DB` 和 `GENERIC_RESET_SOP`；文件里其他旧的 DTC/维修知识数据不参与五个
远程 RAG Tool 的执行。

## 11. 核心文件职责索引

### 11.1 API 与应用入口

| 文件 | 职责 | 最值得看的内容 |
|---|---|---|
| `app/main.py` | FastAPI 创建、生命周期、中间件、异常处理 | `lifespan()`、`trace_id_middleware()`、`_error_content()` |
| `app/api/v1/router.py` | 聚合 `/api/v1` 路由 | 三个 `include_router` |
| `app/api/v1/endpoints/tools.py` | Tool 发现、契约查询、统一调用 | `invoke_tool()` |
| `app/api/v1/endpoints/rag_proxy.py` | 两个 RAG 原生接口透传 | `_forward()` 与“不校验、不加信封”的边界 |
| `app/api/v1/endpoints/health.py` | 健康检查 | `health()` |
| `app/api/v1/schemas.py` | FastAPI/Pydantic 请求响应模型 | `ToolInvokeRequest.merge_flat_payload()`、`ToolInvokeResponse` |

### 11.2 核心基础设施

| 文件 | 职责 | 最值得看的内容 |
|---|---|---|
| `app/core/registry.py` | handler 注册、契约绑定、Tool 调用总流水线 | `load_contracts()`、`invoke()`、`register_tool()` |
| `app/core/slot_extractor.py` | 从 Agent 大请求中提取当前 Tool 槽位 | `_values_at_path()`、`extract_slots()` |
| `app/core/validation.py` | JSON Schema 校验和输出 `null` 清理 | `validate_against_schema()`、`strip_invalid_nulls()` |
| `app/core/responses.py` | 统一信封、trace/echo 上下文 | `extract_echo_ids()`、`ApiResponse` |
| `app/core/exceptions.py` | 统一业务异常与错误码 | 5 个异常类型 |
| `app/core/discovery.py` | RAG 健康实例实时查询 | `pick_instance()` |
| `app/core/nacos.py` | 本中台注册、重试、注销 | `NacosRegistrar` 生命周期 |
| `app/config.py` | `.env`/环境变量配置 | RAG 地址、超时、Nacos、`skills_dir` |
| `app/core/logging_config.py` | 应用与 uvicorn 控制台日志 | `LOGGING_CONFIG` |
| `app/core/openapi.py` | Swagger 标签和错误示例 | `COMMON_RESPONSES` |

### 11.3 Tool 层

| 文件 | 职责 |
|---|---|
| `app/tools/__init__.py` | 集中导入所有 Tool，触发装饰器自注册 |
| `app/tools/dtc_context.py` | 映射 `dtc_context_service` 到 RAG `dtc-context` |
| `app/tools/dtc_grouping.py` | 映射 `dtc_grouping_service` 到 RAG `dtc-grouping` |
| `app/tools/cause_ranking.py` | 映射原因排序接口，并使用独立 50 秒超时 |
| `app/tools/diagnostic_planning.py` | 映射诊断规划接口 |
| `app/tools/repair_planning.py` | 映射维修规划接口 |
| `app/tools/diagnose.py` | 映射综合诊断接口，使用 `/api/v1` 路径和 60 秒超时 |
| `app/tools/dtc_cause_cards.py` | 映射原因处置卡接口，使用 `/api/v1` 路径和 60 秒超时 |
| `app/tools/maintenance_light_reset.py` | 本地保养归零 guide/execute 状态处理 |
| `app/tools/argument_normalizers.py` | 工具专属旧格式归一化扩展点；当前注册表为空 |
| `app/tools/base.py` | 本地工具使用的简单文本匹配辅助函数 |
| `app/tools/knowledge.py` | 本地模拟知识数据；当前保养 SOP 最重要 |

### 11.4 契约层

每个 `myskills/<skill>/` 目录包含：

- `SKILL.md`：给 Agent/开发人员看的工具使用语义；
- `tool-schema.json`：中台运行时真正读取的工具契约。

修改 Tool 入参或出参时，优先确认 `tool-schema.json`。只修改 Pydantic 示例或 README 不会改变
注册中心的实际校验行为。

## 12. 验证脚本与同步脚本

### 12.1 当前最重要的脚本

#### `sync_rag_five_tool_contracts.py`

用途：从指定 RAG 服务同步五个强类型 Tool 的 input/output Schema 到本地 `myskills`。

重点逻辑：

- `CONTRACT_PATHS`：Tool 与本地契约文件的映射；
- `EXTRACT_MAPPING`：同步后由中台追加的 `x-extract`；
- `main()`：读取 RAG OpenAPI/Tool 契约，覆盖本地五份 Schema。

这是会写文件的同步脚本。运行前应确认 RAG 版本和 Git 工作区，运行后必须查看契约 diff 并跑
`tests/test_five_tool_contracts.py`、`tests/test_orchestrator_examples.py` 和完整测试。

#### `verify_rag_runtime_contracts.py`

用途：直接访问 RAG，检查五个本地 Schema 是否与 RAG 发布契约一致，再用实际请求验证返回值
是否满足本地 `output_schema`。

重点逻辑：

- 先比较本地与远程 input/output Schema；
- 调用 Context、Grouping；
- 从 Grouping 返回中选择一个 `groups[].dtc_codes`；
- 再调用 Cause、Diagnostic、Repair；
- 用 `jsonschema` 校验每个实际响应。

#### `verify_rag_chain.py`

用途：通过已经启动的 Tool 中台调用五工具，验证完整的“中台 → RAG”链路，而不是直接请求 RAG。

重点逻辑：

- `invoke()` 检查中台信封 `code`；
- Context/Grouping 使用完整 DTC；
- 后三个 Tool 使用一个完整分组的 `dtc_codes`。

#### `verify_diagnose.py`

用途：读取 `examples/diagnose_invoke.json`，调用本地中台的 `diagnose_service/invoke`。
它是简单的人工冒烟脚本，没有像测试文件那样完整断言。

### 12.2 历史同步辅助文件

仓库根目录下 `_sync_*.py`、`_remote*.json`、`_*diff.txt` 主要用于早期 diagnoses 和
dtc-cause-cards 契约抓取、对比与同步。它们不参与服务启动和请求处理。除非正在维护对应旧契约，
首次阅读项目时可以跳过。

## 13. 测试文件怎么读

| 测试文件 | 保证的核心行为 |
|---|---|
| `test_five_tool_contracts.py` | 五工具只接受 RAG 0.8.0 公共输入，并能从编排快照提取槽位 |
| `test_registry_slot_extraction.py` | 注册中心在校验前执行嵌套槽位提取 |
| `test_invoke_argument_filtering.py` | 有无 `x-extract` 时都能过滤未知 Agent 字段 |
| `test_invoke_echo_request.py` | ID 匹配、类型限制、成功/错误回显、并发隔离、OpenAPI 示例 |
| `test_success_response_envelope.py` | RAG 业务数据只包装一次，放在中台 `data` 中 |
| `test_error_response_envelope.py` | 上游错误仍保持中台统一信封和 echo |
| `test_rag_client.py` | trace 透传、上游 502/503/504 映射、读取超时映射 |
| `test_grouping_forwarding.py` | Grouping 只发一次规范请求，不再逐 DTC 回调补全 |
| `test_cause_ranking_timeout.py` | Cause Ranking 使用独立超时配置 |
| `test_orchestrator_examples.py` | 发给编排层的示例持续符合发布契约 |

推荐根据修改范围运行测试：

```powershell
# 完整测试
uv run --extra dev pytest

# 改 echo / 请求模型
uv run --extra dev pytest tests/test_invoke_echo_request.py tests/test_error_response_envelope.py

# 改槽位提取 / 五工具 Schema
uv run --extra dev pytest tests/test_registry_slot_extraction.py tests/test_five_tool_contracts.py

# 改 RAG 客户端
uv run --extra dev pytest tests/test_rag_client.py tests/test_cause_ranking_timeout.py
```

## 14. 常见修改场景

### 14.1 新增一个远程 Tool

1. 在 `myskills/<new-skill>/` 新增 `SKILL.md` 和 `tool-schema.json`。
2. 在 `app/tools/<new_tool>.py` 写 `@register_tool("tool_name")` handler。
3. 在 `app/tools/__init__.py` 导入新模块。
4. 如果入参来自 Agent 嵌套快照，在 `input_schema.x-extract` 声明路径。
5. 增加契约、过滤、RAG 转发和响应校验测试。
6. 更新 README 和联调示例。

### 14.2 调整五工具请求字段

1. 先确认 RAG 发布的新契约；
2. 更新对应 `tool-schema.json`；
3. 必要时更新 `x-extract`；
4. 更新 `examples/orchestrator/README.md` 和 JSON 示例；
5. 跑 Schema、示例和完整测试；
6. 用 `verify_rag_runtime_contracts.py` 验证远端真实响应。

不要只改 `app/api/v1/schemas.py`。它定义的是统一 HTTP 外壳和 Swagger 示例，不是具体 Tool 的
业务入参契约。

### 14.3 增加一种 Agent ID

如果字段名已经是 `id` 或 `*_id`，不需要改代码；动态规则会自动回显。如果希望支持其他命名
风格，例如 `requestId`，才需要修改 `is_echo_id_key()`，同时补齐类型、错误和并发测试。

### 14.4 接入真实保养归零设备

设备适配层的明确集成点在 `maintenance_light_reset.py` 最后的 execute 成功分支。接入时不能只把
模拟文案替换成 HTTP 调用，还需要定义：设备服务归属、幂等键、超时、设备错误码映射、操作审计、
重复执行保护和真实执行结果的 output schema。

## 15. 故障排查顺序

### 15.1 返回 `40000`

1. 用 `GET /api/v1/tools/{tool_name}` 查看当前实际 `input_schema`；
2. 检查请求使用推荐的 `arguments` 包装；
3. 检查 `arguments` 非空时，业务字段是否误放在顶层；
4. 检查 `x-extract` 路径是否覆盖 Agent 快照形态；
5. 查看错误信息中的字段路径。

### 15.2 返回 `50001`

1. 记录 RAG 原始响应；
2. 与本地 `output_schema` 比较；
3. 运行 `verify_rag_runtime_contracts.py`；
4. 判断是 RAG 返回漂移，还是本地契约未同步；
5. 不要通过关闭输出校验掩盖契约不一致。

### 15.3 返回 `50002` / `50400`

1. 看日志中的最终 RAG URL；
2. 确认 `RAG_BASE_URL` 是否配置；
3. 若走 Nacos，确认 `roxie-supper-rag-service` 有健康实例；
4. 检查该 Tool 使用的是 15s、50s 还是 60s 超时；
5. 用相同参数直接调用 RAG 判断问题位于中台还是上游。

### 15.4 `echo` 不符合预期

1. ID 是否位于请求体顶层；
2. 字段名是否严格为 `id` 或 `_id` 后缀；
3. 值是否为非 `null` 的字符串或整数；
4. 不要把请求体 `trace_id` 与 `X-Trace-Id` 混为一谈；
5. 运行 `tests/test_invoke_echo_request.py`。

## 16. 当前实现中必须知道的限制

- 五工具的诊断、排序和维修知识算法全部在 RAG，不在本仓。
- RAG 实例每次实时查询 Nacos，没有本地实例缓存；这保证新鲜度，但增加一次发现查询开销。
- `RagServiceClient` 是同步 `httpx.Client`；Tool endpoint 是同步函数，由 FastAPI 在线程池执行。
- `x-extract` 是轻量路径解释器，不支持完整 JSONPath 语法。
- `arguments` 为非空对象时不会与顶层业务字段合并，联调时应统一使用推荐格式。
- 原生 `/diagnoses`、`/dtc-cause-cards` 代理绕过 Tool 输入/输出 Schema 和统一响应信封。
- 保养归零 execute 尚未连接真实设备，当前成功结果是模拟数据。
- `sync_rag_five_tool_contracts.py` 会覆盖五份本地契约，必须在干净 Git 分支上运行并审查 diff。
- `app/config.py` 中的配置应通过部署环境或 `.env` 覆盖；生产凭据不应继续依赖源码默认值。

## 17. 最后记住这五个入口

当你以后重新回到这个项目，只需要先定位以下五处：

```text
HTTP 入口：       app/api/v1/endpoints/tools.py::invoke_tool
统一调用流水线： app/core/registry.py::ToolRegistry.invoke
请求字段过滤：   app/core/slot_extractor.py::extract_slots
远程转发：       app/services/rag_client.py::RagServiceClient.invoke
契约真源：       myskills/*/tool-schema.json
```

沿着这五个入口向前后展开，就能覆盖绝大多数开发和排障场景。
