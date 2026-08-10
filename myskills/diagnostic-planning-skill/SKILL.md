---
name: diagnostic-planning
description: 基于 Cause Ranking 输出的候选原因排序，从结构化维修知识中拉取候选检查项并排序，输出当前分析对象下的诊断检查计划。该 Skill 负责检查项拉取与排序、结果分支输出，不负责候选原因排序、根因判断或维修方案生成。
tools:
  - global_tool: diagnostic_planning_service
    description: 基于结构化维修知识、候选原因排序和当前上下文，拉取并排序诊断检查项，输出 ranked_checks 和 result_branches。
    required: true
---

# Diagnostic Planning Skill

## 1. 目标

该 Skill 负责基于 Cause Ranking 输出的候选原因排序，从结构化维修知识中拉取候选检查项，并对检查项进行排序，输出当前分析对象下的诊断检查计划。

当前分析对象可以是：
- **dtc_group**：多个 DTC 组成的分析对象
- **single_dtc**：一个独立 DTC 分析对象（含 DTC Grouping 输出的 independent DTC）
- **symptom_case**：当前没有可用 DTC 作为分析锚点，需基于故障现象进行排查

该 Skill 主要回答：
- 当前分析对象下，应该检查哪些项目？
- 推荐顺序是什么？
- 不同检查结果对应什么下一步动作？

核心链路：

```
当前分析对象 + ranked_causes
  ↓
retrieve_checks：拉取 candidate_checks
  ↓
rank_checks：排序 candidate_checks
  ↓
输出 ranked_checks
```

说明：
- 有 DTC 时，Diagnostic Planning 基于 DTC Group 或 single DTC 输出检查计划
- 无可用 DTC 时，可基于 symptom_case 和候选原因排序输出检查计划
- 故障现象在有 DTC 时作为辅助排序证据，在无 DTC 时才作为分析入口
- `candidate_checks` 是内部中间结果，`ranked_checks` 是对外核心输出

## 2. 触发条件

### 2.1 用户明确提问
- “下一步先查什么？”
- “这个故障怎么排查？”
- “怎么确认是不是某个原因？”
- “怎么确认是不是某个零件坏了？”
- “检查正常后下一步查哪里？”
- “检查异常后下一步怎么处理？”
- “怠速抖动但没有故障码，下一步先查什么？”
- “没有报码，但空调不制冷，该怎么排查？”

### 2.2 链路调用
- Cause Ranking 已输出当前分析对象下的候选原因排序
- Repair Agent 需要给出当前分析对象下的推荐检查项列表
- 用户选择某个 DTC Group、single DTC、symptom_case 或候选原因继续排查
- 当前检查项执行完成，需要根据 `result_branches` 推进下一步
- 检查结果影响候选原因排序，需要回到 Cause Ranking
- 检查结果命中确认分支，需要进入 Repair Planning

## 3. 输入信息

Diagnostic Planning 根据 `operation` 区分内部子能力：

| operation | 含义 |
|-----------|------|
| `retrieve_checks` | 候选检查项拉取 |
| `rank_checks` | 候选检查项排序 |

`operation` 是内部执行指令，不代表对外输出拆成两套业务结果。对外最终输出仍然是排序后的检查项列表。

### 3.1 retrieve_checks 输入

| 字段 | 必要性 | 说明 |
|------|--------|------|
| operation | 必备 | `retrieve_checks` |
| target_type | 必备 | `dtc_group` / `single_dtc` / `symptom_case` |
| group_id | 条件必备 | target_type = `dtc_group` 时必填 |
| dtcs | 条件必备 | target_type = `dtc_group` / `single_dtc` 时必填 |
| symptom_description | 条件必备 | target_type = `symptom_case` 时必填；DTC 场景下可作为可选增强信息 |
| dtc_result | 条件必备 | target_type = `symptom_case` 时必填（`unknown` / `no_dtc`） |
| brand | 条件必备 | 用于匹配品牌相关检查项和诊断流程 |
| system | 条件必备 | 当前分析对象所属系统，用于限定检查项拉取范围 |
| ranked_causes | 必备 | 来自 Cause Ranking，用于根据候选原因反查推荐检查项 |
| related_parts | 条件必备 | 当前分析对象涉及的零件、模块、线路、传感器、执行器或检测对象 |
| vehicle_info | 可选 | 车型、年款、VIN、发动机、配置等 |

说明：
- 结构化维修知识不作为输入字段，而是 Diagnostic Planning 的数据源 / 工具依赖
- DTC Grouping 输出的 independent DTC 进入 Diagnostic Planning 后，统一按 `single_dtc` 处理
- Diagnostic Planning 不重新计算候选原因排序

### 3.2 rank_checks 输入

在 retrieve_checks 输入基础上，增加：

| 字段 | 必要性 | 说明 |
|------|--------|------|
| operation | 必备 | `rank_checks` |
| candidate_checks | 必备 | 由 retrieve_checks 拉取到的候选检查项集合 |
| inspection_results | 可选 | 已有检查结果，用于避免重复推荐或调整检查项顺序 |

`candidate_checks` 应尽量携带：检查项来源、关联 DTC、关联候选原因、相关零件、结构化顺序、前置依赖、判断标准、结果分支、检查成本、来源置信度等排序属性。

首次生成诊断计划时，通常自动串联：

```
retrieve_checks → rank_checks
```

## 4. 处理规则

### 4.1 按 operation 执行不同子能力

```
operation = retrieve_checks
  ↓ 基于当前分析对象和 ranked_causes 拉取候选检查项
  ↓ 生成 candidate_checks

operation = rank_checks
  ↓ 读取 candidate_checks
  ↓ 结合 ranked_causes 和当前上下文排序检查项
  ↓ 输出 ranked_checks
```

- `candidate_checks` 是 retrieve_checks 的中间结果
- `ranked_checks` 是对外核心输出
- Diagnostic Planning 不重新排序候选原因，只排序检查项

### 4.2 retrieve_checks：拉取候选检查项

retrieve_checks 的核心不是从零生成检查步骤，而是从结构化维修知识中拉取候选检查项。

```
当前分析对象 + DTC / 故障现象 + 系统 / 相关零件 + ranked_causes
  ↓
查询结构化维修知识
  ↓
拉取 candidate_checks
```

候选检查项主要来自：
- **DTC → Structured Check Steps**：从已结构化的 DTC 检查项或诊断流程中获取检查项
- **Cause → Recommended Checks**：根据 Cause Ranking 输出的候选原因反查推荐检查项
- **Symptom → Structured Check Steps / Recommended Checks**：symptom_case 场景下，根据故障现象和候选原因拉取检查项

`candidate_checks` 不是最终推荐顺序，只表示当前可用于诊断排查的检查项池。

### 4.3 DTC Group 场景

当 target_type = `dtc_group` 时，应基于 Cause Ranking 输出的合并候选原因，从结构化维修知识中拉取检查项。

优先拉取：
- 能验证高优先级合并候选原因的检查项
- 能覆盖多个 DTC 的检查项
- 能验证多个 DTC 共同相关零件 / 对象的检查项

**DTC Group 场景下，候选检查项必须来自结构化维修知识。若无匹配结果，不调用大模型生成检查项。**

核心原则：优先检查能够验证多个 DTC 共同候选原因或共同相关对象的检查项。

### 4.4 single DTC 场景

应优先从结构化维修知识中拉取该 DTC 对应的检查项。若结构化维修知识中已包含步骤顺序、前置依赖或结果分支，应优先保留这些结构化关系。

未命中结构化检查项时，可使用大模型生成低置信度基础检查方向，但必须标记：
- `check_source = llm_generated`
- `source_confidence = low`
- `uncertainty_note` 必填

大模型兜底检查项仅作为低置信度排查线索，不得替代结构化诊断流程，也不得作为原因确认的唯一依据。

### 4.5 symptom_case 场景

当 `dtc_result = unknown` 时：
- 应优先建议读取 DTC / 扫描车辆
- 可基于故障现象和低置信度候选原因输出初步检查方向
- 检查项置信度应降低，并输出不确定性说明
- 不得表达为无 DTC 场景
- 若后续读取到 DTC，应转入 single_dtc 或 dtc_group 场景重新生成诊断检查计划

当 `dtc_result = no_dtc` 时：
- 可基于故障现象、系统、相关零件和 ranked_causes 拉取检查项
- 优先使用结构化维修知识
- 结构化维修知识无匹配时，可使用大模型低置信度兜底

核心原则：**有 DTC 时，以 DTC 为分析锚点；无 DTC 时，以故障现象为分析锚点；DTC 结果未知时，优先建议读码，只做低置信度预分析。**

### 4.6 rank_checks：输出完整排序检查项列表

rank_checks 应基于 `candidate_checks`、`ranked_causes` 和当前上下文，对候选检查项进行轻量排序。

- `ranked_checks` 的数组顺序代表系统推荐检查顺序
- 第一项是系统建议优先执行的检查项
- 用户可以按照系统推荐顺序执行检查，也可以自行选择某个检查项先执行
- 当检查结果返回后，Repair Agent 根据该检查项的 `result_branches` 命中下一步动作

产品展示上可以默认突出 Top 1 或 Top 3，但数据输出层应保留当前分析对象下的排序检查项列表。

### 4.7 rank_checks：轻量排序规则

排序参考因素包括：
- 检查项来源
- 关联候选原因优先级
- 检查项覆盖的 DTC 或故障现象范围
- 检查项关联的零件 / 相关对象
- 结构化检查项顺序
- 前置依赖关系
- 判断标准是否完整
- 是否存在结果分支
- 检查成本（耗时、操作复杂度、拆装难度、工具要求、安全风险）
- 已有检查结果是否已经覆盖该检查项

排序规则：
- DTC Group 场景下，能验证多个 DTC 共同候选原因或共同相关对象的检查项优先
- single DTC 存在结构化检查项顺序时，优先保留该顺序
- symptom_case 且 `dtc_result = unknown` 时，读取 DTC / 全车扫描应作为优先建议
- 能验证高优先级候选原因的检查项优先
- 已完成且结果明确的检查项不重复推荐
- 大模型兜底生成的检查项默认后置
- 缺少判断标准或结果分支的检查项优先级降低
- 诊断价值相近时，优先推荐检查成本更低、操作更简单、风险更低的检查项
- 检查成本仅作为排序参考因素，不应覆盖结构化顺序、前置依赖、高优先级原因验证和安全边界
- 涉及高风险操作时，不默认推荐用户自行执行

### 4.8 检查结果分支与下一步动作

`ranked_checks` 应尽量为每个检查项携带结果分支 `result_branches`。

```
ranked_checks → 用户 / Tool 执行某个检查项 → 返回检查结果
  ↓ 匹配 check_id → 命中 result_branches → 读取 next_action
```

检查结果归一为三类：

| result_type | 说明 |
|-------------|------|
| normal | 当前检查结果符合该检查项的正常判断条件 |
| abnormal | 当前检查结果满足该检查项的异常判断条件 |
| inconclusive | 当前结果不足以判断正常或异常 |

说明：
- `normal` 不代表故障不存在，也不代表某个候选原因被彻底排除
- `abnormal` 不一定直接等于 `confirmed_cause`，可能只是支持某个候选原因
- `inconclusive` 表示当前结果不足以判断，需要补充信息、重新采集或继续检查

`next_action` 枚举：

| next_action | 说明 |
|-------------|------|
| continue_check | 当前方向仍需进一步检查，可继续执行下一个检查项 |
| update_cause_ranking | 新增证据明显影响候选原因优先级，需要回到 Cause Ranking |
| enter_repair_planning | 当前结果已满足原因确认条件，可进入 Repair Planning |
| ask_user | 缺少必要信息，用户补充后系统仍可继续自动分析 |
| human_support | 高风险、资料不足、工具不可用或系统无法可靠判断，需要人工介入 |

### 4.9 原因状态更新边界

Diagnostic Planning 输出 `ranked_checks` 和 `result_branches` **本身不会改变候选原因状态**。

只有当用户反馈检查结果、Tool 返回检测结果，或系统获得新的诊断证据后，才可基于结果分支推进下一步动作。

如果只是查看检查计划、展开检查项、浏览结果分支，或选择但未执行检查项，**不应**更新 Cause Ranking，不应改变候选原因优先级，不应输出 `confirmed_cause`，也不应进入 Repair Planning。

`confirmed_cause` 只能在检查结果满足结构化判断标准，且证据充分时输出。

## 5. Tool 使用

优先通过全局工具服务完成检查项拉取与排序。

### Tool 契约
- Tool 名称：`diagnostic_planning_service`
- 作用：从结构化维修知识中拉取候选检查项，并结合 ranked_causes 和当前上下文排序
- 输入：见 `tool-schema.json`；通过 `operation` 区分 `retrieve_checks` 与 `rank_checks`
- 输出：`retrieve_checks` 返回 `candidate_checks`；`rank_checks` 返回 `diagnostic_plan`（含 `ranked_checks`）

### 兜底策略

| 场景 | 处理方式 |
|------|----------|
| 缺少 Cause Ranking 结果 | 先回到 Cause Ranking |
| dtc_group 无结构化检查项 | 不调用大模型兜底，输出检查项数据缺失 |
| single_dtc 无结构化检查项 | 大模型低置信度兜底，标记 `llm_generated` |
| symptom_case 无结构化检查项 | 大模型低置信度兜底，标记 `llm_generated` |
| dtc_result = unknown | 优先建议读取 DTC / 扫描车辆 |
| 判断标准或结果分支缺失 | 不得输出 `confirmed_cause` |
| 高风险系统 | 提示风险，必要时 `human_support` |

## 6. 输出结构

核心输出为 `diagnostic_plan` + `ranked_checks`。

### 6.1 顶层输出字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| diagnostic_plan | 必备 | 本次生成的诊断检查计划整体 |
| uncertainty_note | 条件必备 | 信息不足、低置信度、结果不明确或兜底生成时输出 |
| missing_required_info | 条件必备 | 缺失的必要信息 |

`diagnostic_plan` 内字段：

| 字段 | 必要性 | 说明 |
|------|--------|------|
| target_type | 必备 | `dtc_group` / `single_dtc` / `symptom_case` |
| group_id | 条件必备 | DTC Group 时输出 |
| dtcs | 条件必备 | DTC 场景输出；symptom_case 可为空 |
| symptom_description | 条件必备 | symptom_case 时输出 |
| dtc_result | 条件必备 | symptom_case 时输出 |
| system | 条件必备 | 当前分析对象所属系统 |
| ranked_checks | 必备 | 排序后的检查项列表，第一项为当前建议优先执行的检查项 |
| uncertainty_note | 条件必备 | 整体不确定性说明 |

说明：顶层不设置 `next_action`。检查前看 `ranked_checks` 的推荐顺序，检查后看对应检查项的 `result_branches.next_action`。

### 6.2 ranked_checks 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| check_id | 必备 | 检查项唯一标识 |
| check_name | 必备 | 当前检查项名称 |
| check_source | 必备 | `structured_repair_knowledge` / `llm_generated` |
| linked_dtcs | 条件必备 | 该检查项覆盖或关联的 DTC |
| linked_causes | 条件必备 | 该检查项用于验证的候选原因 |
| related_parts | 条件必备 | 当前检查项涉及的相关对象 |
| check_type | 可选 | 数据流读取 / 外观检查 / 电路测量 / 主动测试等 |
| check_goal | 必备 | 说明该检查项用于验证什么 |
| priority | 必备 | `high` / `medium` / `low` |
| check_cost | 可选 | `low` / `medium` / `high` |
| ranking_basis | 必备 | 为什么排在该位置 |
| judgment_summary | 条件必备 | 检查项存在明确判断标准时输出 |
| result_branches | 条件必备 | 正常 / 异常 / 不确定时分别指向下一步动作 |
| required_tools | 可选 | 所需工具或设备能力 |
| source_confidence | 必备 | `high` / `medium` / `low`；大模型兜底必须为 `low` |
| warning_note | 条件必备 | 高风险或低置信度时输出 |
| uncertainty_note | 条件必备 | 信息不足、结果不明确、分支不完整或大模型兜底时输出 |

### 6.3 result_branches 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| result_type | 必备 | `normal` / `abnormal` / `inconclusive` |
| judgment_condition | 条件必备 | 命中该分支的判断条件或阈值 |
| result_interpretation | 必备 | 该检查结果说明什么 |
| affected_causes | 条件必备 | 该结果影响哪些候选原因 |
| next_action | 必备 | `continue_check` / `update_cause_ranking` / `enter_repair_planning` / `ask_user` / `human_support` |
| next_check_id | 条件必备 | 下一步为继续检查时输出 |
| confirmed_cause | 条件必备 | 结果满足确认条件时输出；未命中分支前不改变原因状态 |
| uncertainty_note | 条件必备 | 结果不明确、分支不完整或低置信度时输出 |

### 6.4 check_source 枚举

| 枚举值 | 适用范围 | 说明 |
|--------|----------|------|
| structured_repair_knowledge | 全部场景 | 来源于结构化 DTC 检查项、Cause 推荐检查项、症状检查项等 |
| llm_generated | single_dtc / symptom_case | 结构化维修知识无匹配时的低置信度兜底；**DTC Group 场景不使用** |

### 6.5 输出示例

```json
{
  "diagnostic_plan": {
    "target_type": "dtc_group",
    "group_id": "G1",
    "dtcs": ["P0171", "P0300"],
    "system": "发动机系统",
    "ranked_checks": [
      {
        "check_id": "CHECK_INTAKE_LEAK_001",
        "check_name": "检查进气系统是否存在泄漏",
        "check_source": "structured_repair_knowledge",
        "linked_dtcs": ["P0171", "P0300"],
        "linked_causes": [
          {
            "cause_id": "CAUSE_INTAKE_LEAK_001",
            "cause_name": "进气泄漏",
            "cause_priority": "high",
            "supported_dtcs": ["P0171", "P0300"]
          }
        ],
        "related_parts": ["进气管路", "真空管", "MAF 传感器"],
        "check_type": "visual_inspection",
        "check_goal": "判断进气泄漏是否导致混合气过稀和失火相关故障。",
        "priority": "high",
        "check_cost": "low",
        "ranking_basis": [
          "该检查项用于验证当前高优先级候选原因：进气泄漏",
          "该候选原因同时支持 P0171 和 P0300",
          "该检查项涉及多个 DTC 共同相关的进气系统对象",
          "该检查项成本较低，可作为优先排查项"
        ],
        "judgment_summary": "检查进气管路、真空管及相关连接处是否存在破裂、脱落或漏气。",
        "result_branches": [
          {
            "result_type": "normal",
            "judgment_condition": "未发现进气管路、真空管或连接处存在破裂、脱落、漏气。",
            "result_interpretation": "该结果削弱进气泄漏方向，但不代表完全排除。",
            "affected_causes": [
              { "cause_id": "CAUSE_INTAKE_LEAK_001", "cause_name": "进气泄漏" }
            ],
            "next_action": "update_cause_ranking",
            "uncertainty_note": "若仅做外观检查且未进行烟雾测试，仍可能存在隐性泄漏。"
          },
          {
            "result_type": "abnormal",
            "judgment_condition": "发现进气管路、真空管或连接处存在明显破裂、脱落、漏气。",
            "result_interpretation": "该结果支持进气泄漏方向，并可解释混合气过稀和失火相关故障。",
            "affected_causes": [
              { "cause_id": "CAUSE_INTAKE_LEAK_001", "cause_name": "进气泄漏" }
            ],
            "next_action": "continue_check",
            "next_check_id": "CHECK_FUEL_TRIM_001",
            "uncertainty_note": "建议结合燃油修正数据或烟雾测试进一步确认。"
          },
          {
            "result_type": "inconclusive",
            "judgment_condition": "用户描述不清，或检查条件不满足，无法判断是否存在泄漏。",
            "result_interpretation": "当前检查结果不足以判断进气泄漏方向。",
            "next_action": "ask_user",
            "uncertainty_note": "需要补充更明确的检查结果，或使用烟雾测试进一步确认。"
          }
        ],
        "source_confidence": "medium"
      }
    ]
  }
}
```

### 6.6 信息不足输出示例

```json
{
  "diagnostic_plan": null,
  "uncertainty_note": "当前缺少 Cause Ranking 结果，无法稳定生成诊断检查计划。",
  "missing_required_info": [
    "ranked_causes",
    "当前分析对象",
    "系统"
  ]
}
```

## 7. 边界规则

该 Skill **负责**：
- 根据当前分析对象和 ranked_causes 拉取候选检查项
- 对候选检查项进行排序
- 输出排序后的检查项列表、检查目的、判断标准、结果分支和排序依据
- 通过结果分支为 Repair Agent 提供下一步动作依据
- 为后续 Cause Ranking 更新或 Repair Planning 提供诊断证据输入

该 Skill **不负责**：
- 候选原因拉取、候选原因排序
- 最终根因判断
- 维修方案生成、具体维修步骤、工时费用或维修后验证

核心边界：Diagnostic Planning 只负责把候选原因转成排序检查项和结果分支，**不负责判断哪个原因最可能，也不负责怎么修**。

## 8. 异常与兜底

兜底重点：**不因缺少结构化检查项而编造高置信度检查计划，不因检查结果异常而直接跳到维修方案。**

重点规则：
- 缺少 Cause Ranking 结果时，应先回到 Cause Ranking
- DTC Group 场景下，检查项必须来自结构化维修知识，未命中时不使用大模型兜底
- single_dtc / symptom_case 结构化维修知识无匹配时，可使用大模型低置信度兜底
- `dtc_result = unknown` 时，应优先建议读取 DTC / 扫描车辆
- 大模型兜底检查项必须标记 `check_source = llm_generated`、`source_confidence = low`
- 判断标准或结果分支缺失时，不得输出 `confirmed_cause`
- 只是查看检查计划或结果分支时，不更新原因排序，不确认原因，不进入 Repair Planning
- 涉及高风险系统时，应提示风险，必要时进入人工支持

## 9. 验收标准

- 能正确区分 `retrieve_checks`（拉取候选检查项）与 `rank_checks`（排序候选检查项）
- 能基于当前分析对象、DTC / 故障现象、相关零件和 ranked_causes 从结构化维修知识中拉取候选检查项
- DTC Group 只使用结构化维修知识；single_dtc 和 symptom_case 可在结构化维修知识缺失时低置信度兜底
- 输出完整 `ranked_checks` 列表，而不是只输出单个下一步检查项
- 排序应基于 candidate_checks 携带的结构化属性和 ranked_causes 的候选原因优先级
- 每个检查项应尽量包含 normal / abnormal / inconclusive 三类结果分支和对应 next_action
- 仅查看检查计划不改变原因状态；只有真实检查结果返回后，才可触发原因排序更新或原因确认
