# Agent 请求 ID 过滤与 Echo 回显设计

## 1. 背景与目标

Agent 调用统一工具接口时，可能提交包含业务槽位、会话标识和其他上下文字段的“大请求”：

```text
POST /api/v1/tools/{tool_name}/invoke
```

Tool 中台应继续按照工具契约只提取并转发 RAG 所需槽位，同时保留 Agent 用于请求关联的 ID，并在所有工具调用响应中原样回显。

本次目标：

- 八个 invoke 工具都只向处理器或 RAG 转交当前工具 `input_schema` 声明的槽位；
- 从请求体顶层提取字段名为 `id` 或以 `_id` 结尾的关联标识；
- 所有 `POST .../invoke` 成功和错误响应都包含 `echo` 对象；
- 没有 ID 时返回 `"echo": {}`；
- 保持现有 `code`、`message`、`data`、`trace_id` 语义不变；
- 防止并发请求之间发生 ID 串扰。

## 2. 范围

### 2.1 本次包含

- 统一 Tool invoke 请求模型；
- invoke 请求作用域的 echo 上下文；
- 成功响应、平台错误、未处理异常和请求校验错误的 echo 回显；
- `arguments` 包裹形式与现有扁平请求兼容形式；
- OpenAPI 示例、编排层请求示例和自动化测试。

### 2.2 本次不包含

- 不改变五个 RAG 工具的输入、输出业务 Schema；
- 不把请求体顶层的 Agent ID 元数据转发给 handler 或 RAG；
- 不把未知字段全部回显；
- 不改变 `X-Trace-Id` 的生成和透传规则；
- 不新增会话存储、幂等处理或请求重放能力；
- 不修改 RAG Service 或 Agent 的实现。

## 3. API 契约

### 3.1 推荐请求格式

需要回显的 ID 放在请求体顶层，工具参数放在 `arguments`：

```json
{
  "request_id": "7f7842cb-a055-407c-8b5c-7c36b0c45ff3",
  "session_id": "1120628",
  "tenant_id": "tenant-001",
  "task_id": 1001,
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137", "P0138"],
    "language": "en",
    "agent_private_context": {
      "step": 3
    }
  }
}
```

中台传给 RAG 的请求仅为：

```json
{
  "brand": "丰田",
  "model": "汉兰达",
  "year": 2021,
  "dtc_codes": ["P0136", "P0137", "P0138"],
  "language": "en"
}
```

### 3.2 扁平请求兼容

现有省略 `arguments` 的请求继续支持：

```json
{
  "request_id": "req-001",
  "session_id": "session-001",
  "tenant_id": "tenant-001",
  "brand": "丰田",
  "model": "汉兰达",
  "year": 2021,
  "dtc_codes": ["P0136"],
  "agent_private_context": "not-forwarded"
}
```

请求模型在合并扁平字段时先分离顶层 `id` 和 `*_id`：这些字段只进入请求级 echo，不放入 `arguments`。剩余字段进入现有槽位提取流程，未知字段被丢弃，不会到达 handler 或 RAG。

当请求同时包含 `arguments` 和顶层工具字段时，以 `arguments` 为工具参数来源；echo 始终只扫描请求体顶层，不扫描 `arguments`。如果 Tool 未来确实需要 `group_id` 等业务 ID，应把它放在 `arguments` 内，由 Tool Schema 决定是否转发。

### 3.3 ID 识别规则与类型

第一版按字段名称动态识别顶层 ID：

- 字段名严格等于 `id`；或
- 字段名以 `_id` 结尾，例如 `request_id`、`session_id`、`tenant_id`、`task_id`、`correlation_id`。

字段名匹配区分大小写；`requestId`、`sessionId` 不符合本次规则。

这些字段是 Agent 提供的不透明关联标识，接受 JSON 字符串或整数并原样回显。缺失值或 `null` 不进入 echo。布尔值、对象和数组不是合法 ID，返回现有工具入参错误语义 `code=40000`，且不把非法值放入 echo。

不递归扫描 `arguments`、对象或数组内部的 ID，避免把 `group_id`、`cause_id` 等工具业务数据重复回显。`arguments` 内的业务 ID 不属于 Agent echo 元数据，可以在 Tool Schema 明确消费时正常转发。动态规则意味着顶层 `user_id`、`tenant_id` 等字段也会原样返回，Agent 必须只在顶层提交允许返回给自身的关联标识。

请求体顶层的 `trace_id` 也符合 `_id` 规则，因此会进入 `echo.trace_id`，但它不能覆盖响应信封的 `trace_id`。信封 `trace_id` 仍只由 `X-Trace-Id` 请求头或中台自动生成。

### 3.4 成功响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "contexts": []
  },
  "trace_id": "a1b2c3d4e5f6",
  "echo": {
    "request_id": "7f7842cb-a055-407c-8b5c-7c36b0c45ff3",
    "session_id": "1120628",
    "tenant_id": "tenant-001",
    "task_id": 1001
  }
}
```

`data` 仍只包含工具业务出参，不在 `data` 内混入 Agent 元数据。

### 3.5 缺少 ID

所有 invoke 响应都保留 echo 对象：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "trace_id": "a1b2c3d4e5f6",
  "echo": {}
}
```

只传一个符合规则的 ID 时，echo 只包含该字段，不补其他键或 `null`：

```json
"echo": {
  "request_id": "req-001"
}
```

### 3.6 错误响应

工具入参校验、工具执行、上游错误和未处理异常同样回显合法 ID：

```json
{
  "code": 40000,
  "message": "工具 dtc_context_service 入参校验失败: ...",
  "data": null,
  "trace_id": "a1b2c3d4e5f6",
  "echo": {
    "request_id": "req-001",
    "session_id": "session-001"
  }
}
```

请求体 JSON 解析或请求模型校验失败时，统一转换为 invoke 的 `code=40000` 响应；能够从合法顶层字段提取到的 ID 继续回显，无法解析请求体时返回 `"echo": {}`。

## 4. 架构与数据流

```text
Agent 请求
  │
  ├─ 顶层 id / *_id ──> 名称与标量类型校验 ──> echo_ctx
  │
  └─ arguments 或扁平工具字段
           │
           ▼
       槽位白名单提取
           │
           ▼
       input_schema 校验
           │
           ▼
       handler / RAG
           │
           ▼
       output_schema 校验
           │
           ▼
code + message + data + trace_id + echo
```

### 4.1 请求作用域

新增独立的 `echo_ctx`，语义与现有 `trace_id_ctx` 类似。现有 HTTP middleware 在进入 invoke 请求时完成以下操作：

1. 初始化当前请求 echo 为 `{}`；
2. 从可解析的 JSON 请求体顶层读取 `id` 和 `*_id`；
3. 校验并保存合法 ID；
4. 执行后续路由、工具调用和异常处理；
5. 在 `finally` 中恢复 ContextVar token。

必须使用 token 恢复，不能只调用 `set({})`，否则线程或异步任务复用时可能产生上下文泄漏。

### 4.2 响应构造

- `ToolInvokeResponse` 明确增加必备 `echo` 字段，默认读取当前请求 echo，缺省为 `{}`；
- invoke 成功接口返回 `ToolInvokeResponse`，避免被现有 `response_model` 过滤；
- 全局异常处理器根据请求路径判断是否为 invoke；invoke 错误响应追加 `echo`，其他接口响应结构保持不变；
- 增加 FastAPI 请求校验异常处理，确保合法 JSON 的 invoke 校验错误也使用统一信封；
- `trace_id` 与 echo 相互独立：trace 继续取 `X-Trace-Id`，不接受请求体覆盖。

## 5. 并发与安全

- echo 只接受顶层 `id` 和 `*_id` 标量字段，禁止反射全部请求或递归扫描；
- echo 不进入日志新增项，不输出未知字段或胖请求快照；
- echo 不进入工具 Schema，不转发 handler/RAG；
- 每个请求单独设置并恢复 ContextVar token；
- 并发测试必须证明不同请求的 ID 不串扰；
- ID 仅用于关联回显，不代表已实现幂等、鉴权或会话归属校验。

## 6. 兼容性

- `code`、`message`、`data`、`trace_id` 保持现状；
- `data` 的五工具 RAG 0.7.0 契约不变；
- `/api/v1/tools`、`/api/v1/tools/{tool_name}`、健康检查及 RAG 代理端点不增加 echo；
- 所有 `POST /api/v1/tools/{tool_name}/invoke` 响应新增 `echo`，属于向后兼容的字段扩展，但使用严格“字段完全相等”解析的调用方需要同步更新；
- 原有 `arguments` 请求和扁平请求继续可用。

## 7. 预计代码改动

- `app/core/responses.py`：增加 echo 上下文及安全读取方法；
- `app/core/slot_extractor.py`：无 `x-extract` 的工具也按 `input_schema.properties` 做顶层白名单投影；已有五工具继续使用声明式路径提取；
- `app/api/v1/schemas.py`：声明动态 ID 校验和 invoke echo 响应模型，保持扁平参数兼容；
- `app/main.py`：在请求作用域提取/清理 echo，并补齐 invoke 错误响应；
- `app/api/v1/endpoints/tools.py`：成功响应使用带 echo 的模型，更新 Swagger 示例；
- `tests/`：新增过滤、成功、错误、缺 ID、扁平请求和并发隔离测试；
- `examples/orchestrator/`、`README.md`：更新编排层联调示例和响应说明。

不会修改五份 `myskills/*/tool-schema.json`，因为 echo 属于中台传输信封，不属于 RAG 工具业务出参。

## 8. 验收标准

1. 顶层 `id`、`request_id`、`session_id`、`tenant_id`、`task_id` 等字段均进入 echo，且不进入 handler 或 RAG；
2. 八个工具的 Agent 其他未知字段都不进入 handler 或 RAG 请求；
3. 成功响应包含原样 ID 和 RAG 业务 `data`；
4. 没有 ID 时响应包含 `"echo": {}`；
5. 只传一个 ID 时不补其他键或 `null`；
6. `40000`、`50000`、`50002`、`50200`、`50300`、`50400` 等 invoke 错误响应包含 echo；
7. 非 invoke 接口响应不增加 echo；
8. 并发请求之间无 ID 串扰；
9. 五工具 RAG 0.7.0 契约验证和现有全量测试继续通过；
10. 提供可直接交给编排层的带 ID 请求示例。
