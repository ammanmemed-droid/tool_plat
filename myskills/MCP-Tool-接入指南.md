# roxie-rag-service Tool 接入指南

> 文件名为历史遗留。当前项目不是 MCP Server，也没有暴露 Streamable HTTP 或 SSE MCP 端点。实际实现是 FastAPI REST Tool Provider，可通过 Nacos 注册给 Tool 中台。

## 1. 当前运行时架构

```text
Agent
  ↓
Tool 中台
  ↓ HTTP
roxie-rag-service
  ├─ 工具发现 /api/v1/tools
  ├─ 统一调用 /api/v1/tools/{tool_name}/invoke
  └─ 强类型接口 /api/v1/tool-services/*
        ↓
MySQL + Milvus + Embedding + Reranker + LLM
```

Skill 是 Agent 的静态使用说明，不承载请求转发。`tool-schema.json` 是目标目录保存的静态契约快照；运行时的最终权威契约是服务返回的工具详情。

## 2. 当前五个工具

| 工具名 | 强类型接口 | 能力 |
|---|---|---|
| `dtc_context_service` | `/api/v1/tool-services/dtc-context` | 单个 DTC 结构化上下文 |
| `dtc_grouping_service` | `/api/v1/tool-services/dtc-grouping` | 多 DTC 分组 |
| `cause_ranking_service` | `/api/v1/tool-services/cause-ranking` | 原因检索与排序 |
| `diagnostic_planning_service` | `/api/v1/tool-services/diagnostic-planning` | 检查项检索与诊断计划 |
| `repair_planning_service` | `/api/v1/tool-services/repair-planning` | 维修计划 |

`diagnose_service` 与 `maintenance_light_reset_service` 不在当前 Tool Registry 中。主诊断能力另由 `POST /api/v1/diagnoses` 提供。

## 3. 工具发现

- `GET /api/v1/tools`：列出五个工具
- `GET /api/v1/tools/{tool_name}`：返回 `tool_name`、`tool_kind`、`description`、`skill_name`、`input_schema`、`output_schema`

静态文件与运行时发现结果不一致时，以运行时 schema 和项目源码 `src/dtc_rag/tool_services/models.py` 为准。

## 4. 两套调用入口

### 4.1 统一工具入口

```http
POST /api/v1/tools/{tool_name}/invoke
Content-Type: application/json
```

请求体：

```json
{
  "arguments": {
    "dtc_code": "P0171",
    "brand": "宝马"
  }
}
```

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "trace_id": "ab12cd34ef56"
}
```

`data` 完整保留工具 output schema 的顶层字段；没有值的可选字段返回 `null`。

### 4.2 强类型接口

强类型接口直接接收工具输入对象，并直接返回工具输出对象，不需要 `arguments` 包装，也没有 `{code,message,data,trace_id}` 信封。它们与统一入口调用同一组 handler。

## 5. 错误与缺失信息

统一入口错误码：

| HTTP | code | 含义 |
|---|---:|---|
| 400 | 40000 | `arguments` 不符合 input schema |
| 404 | 40400 | 工具不存在 |
| 502 | 50200 | 上游数据源不可用 |
| 503 | 50300 | 依赖配置不完整 |
| 504 | 50400 | 执行超时 |
| 500 | 50000 | 工具执行失败 |

强类型入口的 schema 错误返回 HTTP 422，运行错误返回对应 5xx API 错误信封。

缺少可恢复的业务信息通常不是 HTTP 错误。服务返回 HTTP 200，将核心结果设为 `null` 或空数组，并通过 `missing_required_info` 与 `uncertainty_note` 说明。请求中的额外字段会被忽略；类型错误和非法枚举仍返回 4xx。

## 6. 推荐串联

```text
dtc_context_service
        ↓
dtc_grouping_service
        ↓
cause_ranking_service（自动检索并排序）
        ↓
diagnostic_planning_service（自动检索并排序检查项）
        ↓
repair_planning_service
```

原因与诊断规划工具的新调用方可以省略旧版 `operation` 和 `target_type`。服务会从 `group_id`、`dtcs` 或 `symptom_description` 推导目标并自动串联内部两阶段。旧调用方仍可显式使用两阶段操作。

## 7. Nacos 注册

启用 `NACOS_ENABLED=true` 后，服务以 `roxie_tool_provider` 元数据注册。关键 metadata 包括：

- `provider_kind`
- `provider_version`
- `tool_names`
- `tool_discovery_path`
- `tool_invoke_path`
- `health_path`

默认服务名为 `roxie-rag-service`，当前 provider 版本为 `0.4.2`。具体 IP、端口、namespace、group 和鉴权通过项目环境变量配置。

## 8. 验证

服务启动后运行：

```powershell
uv run python scripts/verify_tool_services.py
```

验证远程实例：

```powershell
uv run python scripts/verify_tool_services.py `
  --base-url http://<host>:8000
```

脚本会验证工具发现、五工具串联、输出顶层字段和统一响应信封。静态技能目录交付前还应确认：

- Skill 中的工具名与 Registry 一致
- `tool-schema.json` 的字段、必填项和枚举与运行时 schema 一致
- 未实现能力明确标记为不可用
- 没有把 REST Tool Provider 描述成 MCP Server
