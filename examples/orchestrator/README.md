# 编排层五工具联调示例（RAG 0.8.0）

统一调用地址：

```text
POST /api/v1/tools/{tool_name}/invoke
Content-Type: application/json
```

Context、Grouping 使用 full scan 示例；Cause、Diagnostic、Repair 使用 Grouping 返回的一个完整
`groups[].dtc_codes`。本文档已内嵌五个完整请求体，可以直接单文件发送给编排层同事，
无需同时发送其他 JSON 文件。

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

请求 JSON：

```json
{
  "request_id": "orchestration-dtc_context_service-001",
  "session_id": "repair-session-001",
  "tenant_id": "tenant-demo",
  "task_id": 1001,
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137", "P0138", "P0420"],
    "language": "en"
  }
}
```

响应 JSON（结构示例；`contexts` 仅展示一条代表记录，实际可能返回多条）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "partial",
    "message": "已返回部分检索结果，请结合 meta 和 issues 复核。",
    "uncertainty_note": "",
    "missing_required_info": [],
    "contexts": [
      {
        "dtc_code": "P0136",
        "match_level": "year_fallback",
        "dtc_description": "氧传感器电路故障 (B1 S2)",
        "dtc_category": "动力系统",
        "system": "发动机混合动力系统",
        "subsystem": "",
        "trigger_conditions": [
          "发动机运行或点火开关 ON 时，控制单元持续监测到相关信号超出阈值，达到规定时间后存储该 DTC"
        ],
        "related_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
        "related_datastreams": []
      }
    ],
    "issues": [],
    "meta": {
      "brand": "丰田",
      "model": "汉兰达",
      "year": 2021,
      "requested_dtcs": ["P0136", "P0137", "P0138", "P0420"],
      "unmatched_dtcs": [],
      "uncertain_dtcs": [],
      "year_fallback_dtcs": ["P0136", "P0137", "P0138", "P0420"],
      "query_truncated": false,
      "recalled_record_count": 46,
      "requested_language": "en",
      "source_content_languages": ["und"],
      "language_fallback": true,
      "core_version": "mvp-recall-v1",
      "grouping_policy_version": "cause-card-semantic-v1"
    }
  },
  "trace_id": "response-example-dtc_context_service",
  "echo": {
    "request_id": "orchestration-dtc_context_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

### 2. `dtc_grouping_service`

- 地址：`POST /api/v1/tools/dtc_grouping_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/dtc-grouping`
- 用途：把车辆完整 DTC 列表按系统、语义原因和关联部件分组。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入车辆本次扫描得到的完整 DTC 列表；后续三个工具应使用返回的一个完整 `groups[].dtc_codes`。

请求 JSON：

```json
{
  "request_id": "orchestration-dtc_grouping_service-001",
  "session_id": "repair-session-001",
  "tenant_id": "tenant-demo",
  "task_id": 1001,
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137", "P0138", "P0420"],
    "language": "en"
  }
}
```

响应 JSON（结构示例；`groups` 仅展示一条代表记录，实际可能返回多条）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "partial",
    "message": "已返回部分检索结果，请结合 meta 和 issues 复核。",
    "uncertainty_note": "",
    "missing_required_info": [],
    "groups": [
      {
        "group_id": "ad6313c778af",
        "group_name": "后氧传感器相关故障组",
        "representative_dtc": "P0136",
        "dtc_codes": ["P0136", "P0137", "P0138"],
        "dtc_category": "动力系统",
        "dtc_category_code": "P",
        "semantic_family_code": "downstream_oxygen_sensor",
        "system": "发动机混合动力系统",
        "involved_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
        "shared_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
        "group_reason": "semantic_family",
        "grouping_basis": [
          "group_reason=semantic_family",
          "system=发动机混合动力系统",
          "shared_parts=A/F传感器,排气系统,氧传感器,空燃比传感器,线束,连接器",
          "semantic_family=后氧传感器相关故障组"
        ],
        "match_level": "year_fallback",
        "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
        "member_count": 3,
        "record_count": 36
      }
    ],
    "standalone_dtcs": ["P0420"],
    "issues": [],
    "meta": {
      "brand": "丰田",
      "model": "汉兰达",
      "year": 2021,
      "requested_dtcs": ["P0136", "P0137", "P0138", "P0420"],
      "unmatched_dtcs": [],
      "uncertain_dtcs": [],
      "year_fallback_dtcs": ["P0136", "P0137", "P0138", "P0420"],
      "query_truncated": false,
      "recalled_record_count": 46,
      "requested_language": "en",
      "source_content_languages": ["und"],
      "language_fallback": true,
      "core_version": "mvp-recall-v1",
      "grouping_policy_version": "cause-card-semantic-v1"
    }
  },
  "trace_id": "response-example-dtc_grouping_service",
  "echo": {
    "request_id": "orchestration-dtc_grouping_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

### 3. `cause_ranking_service`

- 地址：`POST /api/v1/tools/cause_ranking_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/cause-ranking`
- 用途：对一个 DTC 分组的候选故障原因进行概率排序。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入 Grouping 返回的一个完整 `groups[index].dtc_codes`，不要把多个分组混在一次请求中。

请求 JSON：

```json
{
  "request_id": "orchestration-cause_ranking_service-001",
  "session_id": "repair-session-001",
  "tenant_id": "tenant-demo",
  "task_id": 1001,
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137", "P0138"],
    "language": "en"
  }
}
```

响应 JSON（结构示例；`predictions` 仅展示一条代表记录，实际可能返回多条）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "partial",
    "message": "已返回部分检索结果，请结合 meta 和 issues 复核。",
    "uncertainty_note": "",
    "missing_required_info": [],
    "group": {
      "group_id": "ad6313c778af",
      "group_name": "后氧传感器相关故障组",
      "representative_dtc": "P0136",
      "dtc_codes": ["P0136", "P0137", "P0138"],
      "dtc_category": "动力系统",
      "dtc_category_code": "P",
      "semantic_family_code": "downstream_oxygen_sensor",
      "system": "发动机混合动力系统",
      "involved_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
      "shared_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
      "group_reason": "semantic_family",
      "grouping_basis": [
        "group_reason=semantic_family",
        "system=发动机混合动力系统",
        "shared_parts=A/F传感器,排气系统,氧传感器,空燃比传感器,线束,连接器",
        "semantic_family=后氧传感器相关故障组"
      ],
      "match_level": "year_fallback",
      "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
      "member_count": 3,
      "record_count": 36
    },
    "predictions": [
      {
        "rank": 1,
        "candidate_key": "candidate_91aa3e0f3125",
        "reason": "氧传感器短路",
        "reason_language": "und",
        "probability_percent": 20.0,
        "is_external": true,
        "prediction_source": "local_repair_knowledge",
        "probability_source": "local_assessor",
        "supported_dtcs": ["P0136", "P0137", "P0138"],
        "troubleshooting": "检查项1：检查氧传感器，依据原厂诊断流程判断；异常时更换氧传感器"
      }
    ],
    "local_candidate_count": 6,
    "probability_source": "local_assessor",
    "probability_degraded": true,
    "issues": [],
    "meta": {
      "brand": "丰田",
      "model": "汉兰达",
      "year": 2021,
      "requested_dtcs": ["P0136", "P0137", "P0138"],
      "unmatched_dtcs": [],
      "uncertain_dtcs": [],
      "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
      "query_truncated": false,
      "recalled_record_count": 36,
      "requested_language": "en",
      "source_content_languages": ["und"],
      "language_fallback": true,
      "core_version": "mvp-recall-v1",
      "grouping_policy_version": "cause-card-semantic-v1"
    }
  },
  "trace_id": "response-example-cause_ranking_service",
  "echo": {
    "request_id": "orchestration-cause_ranking_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

### 4. `diagnostic_planning_service`

- 地址：`POST /api/v1/tools/diagnostic_planning_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/diagnostic-planning`
- 用途：为一个 DTC 分组生成静态诊断检查项和判断依据。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入 Grouping 返回的一个完整 `groups[index].dtc_codes`。

请求 JSON：

```json
{
  "request_id": "orchestration-diagnostic_planning_service-001",
  "session_id": "repair-session-001",
  "tenant_id": "tenant-demo",
  "task_id": 1001,
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137", "P0138"],
    "language": "en"
  }
}
```

响应 JSON（结构示例；`static_checks` 仅展示一条代表记录，实际可能返回多条）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "partial",
    "message": "已返回部分检索结果，请结合 meta 和 issues 复核。",
    "uncertainty_note": "",
    "missing_required_info": [],
    "group": {
      "group_id": "ad6313c778af",
      "group_name": "后氧传感器相关故障组",
      "representative_dtc": "P0136",
      "dtc_codes": ["P0136", "P0137", "P0138"],
      "dtc_category": "动力系统",
      "dtc_category_code": "P",
      "semantic_family_code": "downstream_oxygen_sensor",
      "system": "发动机混合动力系统",
      "involved_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
      "shared_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
      "group_reason": "semantic_family",
      "grouping_basis": [
        "group_reason=semantic_family",
        "system=发动机混合动力系统",
        "shared_parts=A/F传感器,排气系统,氧传感器,空燃比传感器,线束,连接器",
        "semantic_family=后氧传感器相关故障组"
      ],
      "match_level": "year_fallback",
      "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
      "member_count": 3,
      "record_count": 36
    },
    "static_checks": [
      {
        "check_id": "check_640acf64435b",
        "check_item": "检查项1：检查氧传感器，依据原厂诊断流程判断；异常时更换氧传感器",
        "linked_dtcs": ["P0136", "P0137", "P0138"],
        "linked_local_causes": ["氧传感器短路"],
        "judgment_basis": "正常",
        "operation_tip": "检查项2",
        "required_tools": [],
        "initial_priority": "high"
      }
    ],
    "predictions": [
      {
        "rank": 1,
        "candidate_key": "candidate_91aa3e0f3125",
        "reason": "氧传感器短路",
        "reason_language": "und",
        "probability_percent": 25,
        "is_external": true,
        "prediction_source": "local_repair_knowledge",
        "probability_source": "local_assessor",
        "supported_dtcs": ["P0136", "P0137", "P0138"],
        "troubleshooting": "检查项1：检查氧传感器，依据原厂诊断流程判断；异常时更换氧传感器"
      }
    ],
    "probability_source": "local_assessor",
    "probability_degraded": true,
    "issues": [],
    "meta": {
      "brand": "丰田",
      "model": "汉兰达",
      "year": 2021,
      "requested_dtcs": ["P0136", "P0137", "P0138"],
      "unmatched_dtcs": [],
      "uncertain_dtcs": [],
      "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
      "query_truncated": false,
      "recalled_record_count": 36,
      "requested_language": "en",
      "source_content_languages": ["und"],
      "language_fallback": true,
      "core_version": "mvp-recall-v1",
      "grouping_policy_version": "cause-card-semantic-v1"
    }
  },
  "trace_id": "response-example-diagnostic_planning_service",
  "echo": {
    "request_id": "orchestration-diagnostic_planning_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

### 5. `repair_planning_service`

- 地址：`POST /api/v1/tools/repair_planning_service/invoke`
- 对应 RAG 接口：`POST /api/v1/tool-services/repair-planning`
- 用途：为一个 DTC 分组生成维修方案、关联部件和维修后验证要求。
- 请求参数：使用上述五个通用 `arguments` 字段。
- `dtc_codes`：传入 Grouping 返回的一个完整 `groups[index].dtc_codes`。

请求 JSON：

```json
{
  "request_id": "orchestration-repair_planning_service-001",
  "session_id": "repair-session-001",
  "tenant_id": "tenant-demo",
  "task_id": 1001,
  "arguments": {
    "brand": "丰田",
    "model": "汉兰达",
    "year": 2021,
    "dtc_codes": ["P0136", "P0137", "P0138"],
    "language": "en"
  }
}
```

响应 JSON（结构示例；`repair_guides` 仅展示一条代表记录，实际可能返回多条）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "partial",
    "message": "已返回部分检索结果，请结合 meta 和 issues 复核。",
    "uncertainty_note": "",
    "missing_required_info": [],
    "group": {
      "group_id": "ad6313c778af",
      "group_name": "后氧传感器相关故障组",
      "representative_dtc": "P0136",
      "dtc_codes": ["P0136", "P0137", "P0138"],
      "dtc_category": "动力系统",
      "dtc_category_code": "P",
      "semantic_family_code": "downstream_oxygen_sensor",
      "system": "发动机混合动力系统",
      "involved_parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
      "parts": ["A/F传感器", "排气系统", "氧传感器", "空燃比传感器", "线束", "连接器"],
      "group_reason": "semantic_family",
      "grouping_basis": [
        "group_reason=semantic_family",
        "system=发动机混合动力系统",
        "shared_parts=A/F传感器,排气系统,氧传感器,空燃比传感器,线束,连接器",
        "semantic_family=后氧传感器相关故障组"
      ],
      "match_level": "year_fallback",
      "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
      "member_count": 3,
      "record_count": 36
    },
    "repair_guides": [
      {
        "guide_id": "guide_5b63fcb9df97",
        "local_cause_name": "氧传感器短路",
        "dtc_codes": ["P0136", "P0137", "P0138"],
        "repair_steps": "方案1：更换氧传感器",
        "repair_method": "按维修手册拆卸并更换氧传感器，装复后清除故障码并进行功能验证",
        "parts": ["氧传感器"],
        "required_tools": [],
        "warning_note": "",
        "post_repair_verification": [],
        "requires_confirmation": true
      }
    ],
    "predictions": [
      {
        "rank": 1,
        "candidate_key": "candidate_91aa3e0f3125",
        "reason": "氧传感器短路",
        "reason_language": "und",
        "probability_percent": 25,
        "is_external": true,
        "prediction_source": "local_repair_knowledge",
        "probability_source": "local_assessor",
        "supported_dtcs": ["P0136", "P0137", "P0138"],
        "troubleshooting": "检查项1：检查氧传感器，依据原厂诊断流程判断；异常时更换氧传感器"
      }
    ],
    "probability_source": "local_assessor",
    "probability_degraded": true,
    "issues": [],
    "meta": {
      "brand": "丰田",
      "model": "汉兰达",
      "year": 2021,
      "requested_dtcs": ["P0136", "P0137", "P0138"],
      "unmatched_dtcs": [],
      "uncertain_dtcs": [],
      "year_fallback_dtcs": ["P0136", "P0137", "P0138"],
      "query_truncated": false,
      "recalled_record_count": 36,
      "requested_language": "en",
      "source_content_languages": ["und"],
      "language_fallback": true,
      "core_version": "mvp-recall-v1",
      "grouping_policy_version": "cause-card-semantic-v1"
    }
  },
  "trace_id": "response-example-repair_planning_service",
  "echo": {
    "request_id": "orchestration-repair_planning_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

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
  --data-raw '{"request_id":"orchestration-dtc_grouping_service-001","session_id":"repair-session-001","tenant_id":"tenant-demo","task_id":1001,"arguments":{"brand":"丰田","model":"汉兰达","year":2021,"dtc_codes":["P0136","P0137","P0138","P0420"],"language":"en"}}'
```

五个接口的成功响应都包含 `code`、`message`、`data`、`trace_id` 和 `echo`。中台外层
`code=0` 表示 Tool 调用完成；业务结果读取 `data.status`，业务提示读取 `data.message`。RAG 返回的
完整业务对象位于 `data`，不会再嵌套一层业务信封。上面的响应 JSON 来自当前联调数据，
业务内容会随车辆、故障码和知识库数据变化，联调时应重点核对字段结构和类型。
未提交任何匹配 ID 时，invoke 响应仍包含 `"echo": {}`。成功和错误响应使用相同回显规则。
