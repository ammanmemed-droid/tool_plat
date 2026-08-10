---
name: diagnose-skill
description: 通过 diagnose_service 工具调用 roxie-rag-service 的 POST /api/v1/diagnoses REST 主接口，执行自然语言上下文提取、四路召回、RRF 融合、DTC 分组、规则排序与可选 Cross-Encoder 精排。用于一次获得诊断检索上下文、分组和各组候选原因。
---

# Diagnose REST API

## 可用性

当前项目已注册 `diagnose_service` 全局工具服务（远程代理）：

- 统一调用：`POST /api/v1/tools/diagnose_service/invoke`
- 上游实现：roxie-rag-service 的 `POST /api/v1/diagnoses`（经 Nacos 服务发现转发）
- 上游 Swagger：`GET /docs`
- 上游就绪检查：`GET /api/v1/ready`

该接口含 LLM 槽位提取 + 多路召回 + 精排，耗时长于普通工具，中台使用独立的 `DIAGNOSE_TIMEOUT`（默认 60s）。

## 输入

必填：

- `query`：去除首尾空白后必须非空，最长 500 字符

可选：

- `vehicle_info.brand`
- `vehicle_info.model`
- `vehicle_info.year`：4 位数字
- `vehicle_info.dtc_category`
- `vehicle_info.system`
- `vehicle_info.dtc_codes`：最多 10 个
- `vehicle_info.vin`
- `top_n`：1–20，默认 5
- `enable_reranker`：默认 `true`

请求中的附加字段会被忽略。若同时提供 `dtc_category` 与 DTC，一级分类必须与所有 DTC 首字母一致。

```json
{
  "query": "福特蒙迪欧2016款报P2089加速无力",
  "vehicle_info": {
    "brand": "福特",
    "model": "蒙迪欧",
    "year": "2016",
    "dtc_codes": ["P2089"]
  },
  "top_n": 5,
  "enable_reranker": true
}
```

## 输出

响应字段：

- `request_id`
- `context`：可能为 `null`
- `groups`
- `results`
- `elapsed_ms`
- `reranker_degraded`
- `uncertainty_note`
- `missing_required_info`

`groups[]` 的实际共享零件字段名是 `group_names`，不是旧字段 `shared_parts`。`group_reason` 的实际枚举为 `same_code`、`same_system_shared_parts`、`shared_parts`、`standalone`。

`results[].ranked_causes[]` 包含：

- `rank`、`record_id`、`dtc_code`、`dtc_category`
- `possible_cause`、`recommended_check`
- `repair_solution`、`repair_method`、`parts`
- `labor_hours`、`price`、`oem_doc`、`oem_doc_url`
- `final_score`、`relevance_score`、`rule_score`
- `score_source`、`score_breakdown`

当 `reranker_degraded = true` 时，`relevance_score = null`、`score_source = rule_fallback`，`final_score` 使用规则分，并跳过断崖截断。不要把降级结果描述为 Cross-Encoder 评分。

## 边界

- 该接口返回检索与排序结果，不确认最终根因。
- 它是一次性综合检索入口，与五工具分步串联链路（context → grouping → ranking → planning → repair）互为补充，按需选用。
- `request_id` 与响应头 `X-Request-ID` 一致，用于排查链路。
