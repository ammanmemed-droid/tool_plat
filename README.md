# Roxie Tool 中台（roxie-router-service）

基于 FastAPI + Python 3.13 + uv 的工具中台，将 `myskills/` 下 8 个 Skill 声明的
全局工具服务实现并统一暴露给 Agent 发现与调用，同时注册到 Nacos 供 Agent 服务发现。

## 架构与调用链

```
Agent（独立 API 服务）
   │  ① 通过 Nacos 按 service-name 发现本中台
   │  ② GET  /api/v1/tools              工具发现（摘要列表）
   │  ③ GET  /api/v1/tools/{tool_name}  获取完整契约（input/output schema）
   │  ④ POST /api/v1/tools/{tool_name}/invoke  统一调用
   ▼
Tool 中台（本项目）
   │  启动时导入 app.tools 自注册 handler，
   │  扫描 myskills/*/tool-schema.json 绑定契约（唯一契约来源），
   │  槽位提取 -> 入参校验 -> 转发 -> null 规范化 -> 出参校验
   ▼
roxie-supper-rag-service（Nacos 发现，全部远程工具）
    POST /api/v1/tool-services/dtc-context
    POST /api/v1/tool-services/dtc-grouping
    POST /api/v1/tool-services/cause-ranking
    POST /api/v1/tool-services/diagnostic-planning
    POST /api/v1/tool-services/repair-planning
    POST /api/v1/diagnoses
    POST /api/v1/dtc-cause-cards
```

## 已实现工具

| tool_name | 实现方式 | 远程端点 / 说明 |
|---|---|---|
| `dtc_context_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/tool-services/dtc-context` |
| `dtc_grouping_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/tool-services/dtc-grouping` |
| `cause_ranking_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/tool-services/cause-ranking` |
| `diagnostic_planning_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/tool-services/diagnostic-planning` |
| `repair_planning_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/tool-services/repair-planning` |
| `diagnose_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/diagnoses`（综合诊断：LLM 槽位提取 + 多路召回 + 精排） |
| `dtc_cause_cards_service` | 远程代理 | `roxie-supper-rag-service` → POST `/api/v1/dtc-cause-cards`（DTC 原因处置卡片：按品牌+车型分组 + 去重原因 + 检查/维修/验证，支持 strict / same_brand_fallback 匹配策略） |
| `maintenance_light_reset_service` | 本地实现 | 保养归零 SOP 指引（guide）与授权执行（execute） |

远程代理工作机制：
- **五工具 0.7.0 公共输入**：Context / Grouping / Cause / Diagnostic / Repair 均使用
  `brand + model + dtc_codes`，可选 `year + language`；中台可从编排层快照提取这些字段，
  仅把白名单字段发送给 RAG；
- **服务发现**：每次调用实时从 Nacos 查询 `roxie-supper-rag-service`
  健康实例并随机挑选，不缓存实例列表
  （配置 `RAG_BASE_URL` 可直连跳过发现，用于联调/应急）；
- **响应兼容**：支持远端裸结果或 `{code, message, data}` 信封两种形态；
- **null 规范化**：远端对未填充可选字段返回的 `null` 按契约视为缺省后再校验
  （支持契约内本地 `$ref` 解析）；
- **独立超时**：`cause_ranking_service` 使用 `CAUSE_RANKING_TIMEOUT`（默认 50s）；
  `diagnose_service` / `dtc_cause_cards_service` 使用 `DIAGNOSE_TIMEOUT`（默认 60s），
  其余工具使用 `RAG_TIMEOUT`（默认 15s）；
- **错误处理**：RAG 的 502 / 503 / 504 分别映射为 `code=50200 / 50300 / 50400`，
  其他执行错误沿用中台现有错误码。

## 快速开始

```bash
uv sync                 # 安装依赖（自动使用 .python-version 指定的 3.13）
cp .env.example .env    # 按需修改配置
uv run python -m app.main
```

启动后访问：

- **Swagger UI**: http://localhost:8000/docs （也可直接访问 http://localhost:8000/ 自动跳转）
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json
- 健康检查: http://localhost:8000/api/v1/health
- 工具发现: http://localhost:8000/api/v1/tools

## 调用示例

```bash
# 发现工具契约
curl http://localhost:8000/api/v1/tools/dtc_context_service

# 调用工具
curl -X POST http://localhost:8000/api/v1/tools/dtc_context_service/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"brand": "丰田", "model": "汉兰达", "year": 2021, "dtc_codes": ["P0136", "P0137"], "language": "en"}}'
```

编排层五工具完整示例见 `examples/orchestrator/`。

## 测试

```bash
# 单元测试 + API 集成测试（无需启动服务）
uv sync --extra dev
uv run pytest tests/ -v

# 远程链路冒烟验证（需先启动服务，且上游服务已注册 Nacos）
uv run python -m app.main
uv run python verify_rag_chain.py   # RAG 0.7.0 五工具
uv run python verify_diagnose.py    # diagnose_service
```

## 注册与发现设计

- **工具注册**：业务工具以 `@register_tool(tool_name)` 装饰器自注册 handler；
  启动时扫描 `myskills/*/tool-schema.json` 按 `tool_name` 绑定契约，
  契约是入参/出参校验的唯一依据（对应《MCP-Tool-接入指南》第 4 节）。
- **服务注册**：启动时注册为 Nacos 实例（默认 `roxie-router-service`），
  关闭时自动注销；Nacos 不可达不阻断本地启动。
  保活为双保险：SDK gRPC 长连接自动保活（5s 健康检查 + 断线 redo 重注册），
  应用层再按 `NACOS_REREGISTER_INTERVAL`（默认 30s）周期性重新注册
  （幂等 upsert），临时实例被服务端摘除后可自动恢复上线。
- **Agent 发现**：Agent 经 Nacos 拿到中台地址后，用 `/api/v1/tools` 系列接口
  完成工具发现、契约获取与统一调用；响应统一为
  `{code, message, data, trace_id}` 信封。
