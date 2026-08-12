# `/invoke` 请求体日志设计

## 1. 目标

在不改变 Agent、Tool 中台和 RAG 接口行为的前提下，为联调和故障排查提供完整的 Tool 调用请求入参日志。

## 2. 记录范围

仅处理以下请求：

```text
POST /api/v1/tools/{tool_name}/invoke
```

记录该请求的 JSON Body，包括 `arguments` 及 Agent 附带的其他字段。以下内容不记录：

- HTTP Header；
- Authorization、Cookie；
- Query 参数；
- 非 `/invoke` 接口请求体；
- RAG 上游请求和响应正文；
- Tool 执行结果正文。

## 3. 配置

新增配置：

```text
LOG_INCLUDE_REQUEST_BODY=false
LOG_REQUEST_BODY_MAX_BYTES=65536
```

- 默认关闭，避免生产环境无意持久化请求数据；
- 开启后仅对 `/invoke` 生效；
- 最大记录 64 KiB；超过上限时只记录前 64 KiB，并标记已截断；
- 非法或非 JSON 请求不输出正文，只记录解析状态。

## 4. 日志结构

JSON 日志增加：

```json
{
  "event": "tool.invoke.request",
  "tool_name": "dtc_context_service",
  "http_method": "POST",
  "http_path": "/api/v1/tools/dtc_context_service/invoke",
  "request_body": "{\"arguments\":{\"brand\":\"丰田\",\"model\":\"汉兰达\",\"year\":2021,\"dtc_codes\":[\"P0136\"]},\"request_id\":\"request-001\",\"session_id\":\"session-001\"}",
  "request_body_truncated": false
}
```

请求日志与现有 `tool.invoke.completed` 完成日志分开：开启请求体日志后，一次成功调用产生一条请求日志和一条完成摘要；关闭时保持现有单条完成摘要。

`request_body` 固定为字符串类型，内容是单行紧凑 JSON。这样即使内容被截断，外层结构化日志仍是合法 JSON；text 格式也使用相同的单行内容，避免换行注入。

## 5. 数据读取

现有中间件已经为 echo 提取调用 `await request.json()`。实现复用该解析结果，不再次读取网络流，也不改变 FastAPI 后续读取请求体的行为。

请求体按 UTF-8 JSON 紧凑序列化计算日志大小。字段名、字段值、对象字段顺序和数组顺序保持不变，仅去除无业务含义的空格和换行；因此这里的“原样”指完整保留 Agent 提交的 JSON 数据，而不是记录 HTTP 原始字节流。

超过上限时按 UTF-8 字符边界截取日志字符串，避免产生乱码。截断只影响日志，不修改实际请求对象，也不影响槽位提取、校验、echo 或 RAG 转发。

## 6. 安全边界

开启该配置表示部署方明确接受请求体可能包含 VIN、会话 ID、用户输入及其他业务字段并进入日志平台。配置默认关闭。

即使开启，也不读取或输出 Header、Cookie、Authorization。日志格式化器不通过 `str(object)` 序列化任意对象，只接受经过专用逻辑紧凑序列化并限制长度的请求体字符串。

日志平台应限制访问权限和保存周期。关闭配置即可停止新增请求体日志，无需回滚代码。

## 7. 性能

- 关闭时只增加一次布尔配置判断；
- 开启时每个 `/invoke` 请求增加一次最多 64 KiB 的紧凑 JSON 序列化和 stdout 写入；
- 不记录响应正文；
- 不递归脱敏；
- 不同步调用远程日志服务。

## 8. 错误处理

- 请求体不是合法 JSON：保留现有 400 响应行为，日志只记录 `request_body_status=invalid_json`；
- 请求体超过 64 KiB：业务请求继续正常处理，日志标记截断；
- 日志序列化失败：不影响业务请求，只记录 `request_body_status=serialization_error`；
- 日志输出失败由 Python logging 自身处理，不改变接口响应。

## 9. 测试与验收

覆盖以下行为：

- 默认关闭时不输出请求体；
- 开启时完整输出 `/invoke` JSON 数据，且仅规范化无业务含义的空白；
- request/session 等 ID 保留；
- Header、Authorization 和 Cookie 不进入日志；
- 非 `/invoke` 请求不输出请求体；
- 超过 64 KiB 时标记截断；
- JSON 和 text 均保持单行；
- Tool 响应、echo、trace_id、错误码和 RAG 参数保持不变；
- 完整测试通过。

## 10. 修改范围

- `app/config.py`：新增两个配置字段；
- `.env.example`：增加配置示例；
- `app/core/log_context.py`：保存当前请求的可记录 JSON 数据或序列化状态；
- `app/core/logging_config.py`：允许结构化输出请求体及状态字段；
- `app/main.py`：在 `/invoke` 请求解析后输出受控请求日志；
- `tests/`：增加请求体日志行为测试。

不修改 Tool Schema、接口请求/响应模型、RAG 客户端、服务发现或 Dockerfile。

## 11. 回滚

优先设置：

```text
LOG_INCLUDE_REQUEST_BODY=false
```

即可立即停止记录。若仍需代码回滚，回滚本功能提交；Agent、RAG 和 Tool 契约无需同步回滚。
