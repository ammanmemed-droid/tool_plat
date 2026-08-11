# 编排层五工具联调示例（RAG 0.7.0）

统一调用地址：

```text
POST /api/v1/tools/{tool_name}/invoke
Content-Type: application/json
```

Context、Grouping 使用 full scan 示例；Cause、Diagnostic、Repair 使用 Grouping 返回的一个完整
`groups[].dtc_codes`。五个请求文件均可直接作为请求体。

中台通过 Nacos 服务名 `roxie-supper-rag-service` 发现 RAG；当前联调直连地址为
`http://172.16.67.169:8000`。编排层统一调用 Tool 中台 `/invoke`，不直接调用 RAG。

| Tool 工具 | Tool 中台接口 | 对应 RAG 强类型接口 |
|---|---|---|
| `dtc_context_service` | `POST /api/v1/tools/dtc_context_service/invoke` | `POST /api/v1/tool-services/dtc-context` |
| `dtc_grouping_service` | `POST /api/v1/tools/dtc_grouping_service/invoke` | `POST /api/v1/tool-services/dtc-grouping` |
| `cause_ranking_service` | `POST /api/v1/tools/cause_ranking_service/invoke` | `POST /api/v1/tool-services/cause-ranking` |
| `diagnostic_planning_service` | `POST /api/v1/tools/diagnostic_planning_service/invoke` | `POST /api/v1/tool-services/diagnostic-planning` |
| `repair_planning_service` | `POST /api/v1/tools/repair_planning_service/invoke` | `POST /api/v1/tool-services/repair-planning` |

请求体顶层字段名为 `id` 或以 `_id` 结尾的字符串/整数会原样回显到 `echo`，但不会进入
Tool 参数或转发给 RAG。只扫描顶层，`arguments` 内的业务 ID 不回显。

## 通用请求结构（推荐格式）

| 位置 | 参数 | 必填 | 类型 | 说明 |
|---|---|---|---|---|
| 顶层 | `id` / `*_id` | 否 | string / integer | Agent 关联 ID，例如 `request_id`、`session_id`、`tenant_id`、`task_id`；只回显到 `echo` |
| 顶层 | `arguments` | 是（推荐格式） | object | Tool 业务参数；中台按当前 Tool Schema 白名单过滤后转发 |

接口仍兼容把工具字段直接放在请求体顶层的旧格式，但编排层联调统一建议使用 `arguments`，
避免 Agent 元数据与 Tool 业务字段混在一起。

五个工具的 `arguments` 字段一致：

| 参数 | 必填 | 类型 | 约束 | 说明 |
|---|---|---|---|---|
| `brand` | 是 | string | 长度 1～64 | 车辆品牌，如 `丰田` |
| `model` | 是 | string | 长度 1～128 | 车辆车型，如 `汉兰达` |
| `year` | 否 | integer / null | 1900～2100，默认 `null` | 车辆年份；已知时建议传入 |
| `dtc_codes` | 是 | string[] | 1～50 项 | 本次工具处理的 DTC 列表，例如 `P0136` |
| `language` | 否 | string | 长度 2～35，默认 `en` | 期望展示语言，建议使用 BCP-47 风格标签 |

`arguments` 内多余字段会被中台过滤。`brand`、`model`、`dtc_codes` 缺失或类型不符合契约时，
中台返回 `code=40000`。

## 各工具请求参数与使用方式

### 1. `dtc_context_service`

- 地址：`POST /api/v1/tools/dtc_context_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/dtc-context`
- 用途：批量查询 DTC 的描述、分类、系统、触发条件、关联部件和数据流上下文。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入车辆本次扫描得到的完整 DTC 列表，可同时传多个故障码。
- 请求文件：[dtc_context_invoke.json](./dtc_context_invoke.json)

### 2. `dtc_grouping_service`

- 地址：`POST /api/v1/tools/dtc_grouping_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/dtc-grouping`
- 用途：把车辆完整 DTC 列表按系统、语义原因和关联部件分组。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入车辆本次扫描得到的完整 DTC 列表；后续三个工具应使用返回的一个完整 `groups[].dtc_codes`。
- 请求文件：[dtc_grouping_invoke.json](./dtc_grouping_invoke.json)

### 3. `cause_ranking_service`

- 地址：`POST /api/v1/tools/cause_ranking_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/cause-ranking`
- 用途：对一个 DTC 分组的候选故障原因进行概率排序。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入 Grouping 返回的一个完整 `groups[index].dtc_codes`，不要把多个分组混在一次请求中。
- 请求文件：[cause_ranking_invoke.json](./cause_ranking_invoke.json)

### 4. `diagnostic_planning_service`

- 地址：`POST /api/v1/tools/diagnostic_planning_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/diagnostic-planning`
- 用途：为一个 DTC 分组生成静态诊断检查项和判断依据。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入 Grouping 返回的一个完整 `groups[index].dtc_codes`。
- 请求文件：[diagnostic_planning_invoke.json](./diagnostic_planning_invoke.json)

### 5. `repair_planning_service`

- 地址：`POST /api/v1/tools/repair_planning_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/repair-planning`
- 用途：为一个 DTC 分组生成维修方案、关联部件和维修后验证要求。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入 Grouping 返回的一个完整 `groups[index].dtc_codes`。
- 请求文件：[repair_planning_invoke.json](./repair_planning_invoke.json)

推荐调用顺序：

```text
dtc_context_service（完整 DTC）
            │
            └─> dtc_grouping_service（完整 DTC）
                         │
                         └─> 选择一个 groups[].dtc_codes
                                      ├─> cause_ranking_service
                                      ├─> diagnostic_planning_service
                                      └─> repair_planning_service
```

示例：

```bash
curl -X POST http://localhost:8000/api/v1/tools/dtc_grouping_service/invoke \
  -H "Content-Type: application/json" \
  -H "X-Trace-ID: orchestration-demo-001" \
  --data-binary @examples/orchestrator/dtc_grouping_invoke.json
```

成功响应统一为：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "groups": [],
    "standalone_dtcs": [],
    "issues": [],
    "meta": null,
    "uncertainty_note": null,
    "missing_required_info": null
  },
  "trace_id": "orchestration-demo-001",
  "echo": {
    "request_id": "orchestration-dtc_grouping_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

RAG 返回的完整业务对象位于 `data`，不会再嵌套一层业务信封。
未提交任何匹配 ID 时，invoke 响应仍包含 `"echo": {}`。成功和错误响应使用相同回显规则。
