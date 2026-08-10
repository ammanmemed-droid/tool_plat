---
name: dtc-cause-cards-skill
description: 通过 dtc_cause_cards_service 工具调用 roxie-rag-service 的 POST /api/v1/dtc-cause-cards 接口，输入品牌、车型与未分组 DTC 列表，一次获得故障分组、全部去重原因及检查/维修/验证信息。适合只需给出车辆和 DTC 列表、快速拿到原因处置卡片的场景。
tools:
  - global_tool: dtc_cause_cards_service
    description: 本地知识库精确查询，按 PCBU 硬边界和规范零部件交集分组，聚合一站式原因处置卡片。
    required: true
---

# DTC Cause Cards Skill

## 1. 目标

该 Skill 将一组未分组 DTC 直接转换为**原因处置卡片**：每个故障组给出共享零件、
去重后的候选原因，以及每个原因的检查项、维修指引、零件工具和维修后验证。

与五工具分步链路（context → grouping → ranking → planning → repair）相比，
该接口是一站式聚合入口：本地知识库精确查询，不调用五工具 HTTP API；
LLM 只补检查判据、操作提示和维修后验证，失败时模板降级。

## 2. 触发条件

- 用户给出多个 DTC，希望直接获得分组和原因处置建议
- 不需要分步确认背景上下文、候选原因排序等中间结果
- 需要面向维修执行的结构化卡片（检查 / 维修 / 验证）

## 3. 输入信息

| 字段 | 必要性 | 说明 |
|------|--------|------|
| brand | 必备 | 目标车辆品牌，1–64 字符 |
| model | 必备 | 目标车型，1–128 字符 |
| dtc_codes | 必备 | 未分组 DTC 列表，1–50 个 |
| vehicle_match_policy | 可选 | 车辆匹配策略：`strict`（默认，仅品牌+车型）/ `same_brand_fallback`（无车型数据时显式降级到同品牌其他车型） |

```json
{
  "arguments": {
    "brand": "宝马",
    "model": "3系",
    "dtc_codes": ["P0171", "P0300"],
    "vehicle_match_policy": "strict"
  }
}
```

## 4. 输出结构

顶层字段：

- `request_id` / `elapsed_ms`
- `groups`：故障组列表
- `unmatched_dtcs`：知识库未命中的 DTC
- `llm_degraded`：`true` 表示 LLM 不可用，维修后验证已使用模板降级
- `uncertainty_note` / `missing_required_info`

`groups[]` 关键字段：

| 字段 | 说明 |
|------|------|
| group_id / group_name / representative_dtc / dtc_codes / record_ids | 分组标识与成员 |
| vehicle_match_level | 组内知识的车辆匹配级别：`strict` / `same_brand_fallback`（存在任一降级 DTC 时为后者） |
| fallback_dtcs | 本组使用同品牌其他车型知识的 DTC 列表；strict 组为空 |
| dtc_level | 组内最严重有效故障等级（1 最严重 ~ 4 最不严重；-1 和空值不参与定级），可空 |
| group_names | 形成分组依据的共享规范零部件（交集） |
| involved_parts | 组内全部知识记录涉及的零部件（并集） |
| group_reason | same_code / same_system_shared_parts / shared_parts / semantic_family / standalone |
| causes | 原因处置卡片列表 |

`groups[].causes[]` 关键字段：

- `cause_id` / `cause_name` / `dtc_codes` / `record_ids`
- `inspection`：`check_item` + `judgment_basis` + `operation_tip`（可空）
- `repair`：`steps`（可空）+ `note`
- `parts_and_tools`：`reference_price` / `required_tools` / `labor_hours`（均可空）
- `verification`：`items[]`（`order` / `check_item` / `expected_result`）+ `generated_by`（`llm` 或 `template_fallback`）

## 5. 边界规则

- 结果来自本地知识库精确匹配，`unmatched_dtcs` 中的 DTC 未参与分组
- 默认 `strict` 策略只命中品牌+车型完全匹配的知识；选择 `same_brand_fallback` 时，降级命中的组会以 `vehicle_match_level` 和 `fallback_dtcs` 显式标记，不得把降级结果描述为车型精确匹配
- 原因按规范名称去重，检查项取来源顺序最靠前的有效值
- `llm_degraded = true` 时不要把验证项描述为 LLM 生成
- 该接口输出处置建议，不代表已确认最终根因
