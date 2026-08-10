---
name: cause-ranking
description: 针对当前分析对象（DTC Group、single DTC 或 symptom_case）拉取并排序候选原因，为 Diagnostic Planning 提供结构化输入。该 Skill 负责候选原因拉取与排序，输出 ranked_causes，不生成诊断检查项或确认最终根因。
tools:
  - global_tool: cause_ranking_service
    description: 基于结构化原因数据、原厂文档检索、案例数据及可选的大模型兜底，完成候选原因拉取与排序。
    required: true
---

# Cause Ranking Skill

## 1. 目标

该 Skill 针对某一个当前分析对象，完成候选原因拉取与候选原因排序，为后续 Diagnostic Planning 提供结构化输入。

当前分析对象可以是：
- **dtc_group**：多个 DTC 组成的分析对象
- **single_dtc**：一个独立 DTC 分析对象（含 DTC Grouping 输出的 independent DTC、用户指定单个 DTC、当前任务中唯一 DTC）
- **symptom_case**：当前没有可用 DTC 作为分析锚点，需基于故障现象进行候选原因分析

该 Skill 主要回答：
- 当前分析对象下有哪些候选原因？
- 在当前证据下应该优先怀疑哪些原因？

核心链路：

```
当前分析对象 + 品牌 / DTC / 故障现象 / 系统 / 相关零件
  ↓
retrieve_causes：拉取 candidate_causes
  ↓
rank_causes：排序 candidate_causes
  ↓
输出 ranked_causes
```

说明：
- DTC 是进入 Cause Ranking 的一种输入，不是唯一输入；故障现象也可作为分析入口。
- 一旦存在可用 DTC，应优先以 DTC 作为分析锚点。
- `candidate_causes` 是内部中间结果；`ranked_causes` 是对外输出结果。
- 排名靠前表示当前证据下更值得优先检查，**不代表该原因已被确认**。

## 2. 触发条件

在以下场景中使用该 Skill：

### 2.1 用户明确提问
- “P0171 最可能是什么原因？”
- “这组发动机故障码最可能是什么导致的？”
- “P0300 和 P0171 这一组优先怀疑什么原因？”
- “已经换过火花塞还是失火，接下来怀疑哪里？”
- “清码后这组故障码又出现了，最可能是什么问题？”
- “怠速抖动但没有故障码，可能是什么原因？”
- “空调不制冷，没有报码，优先怀疑哪里？”
- “车子冷启动困难，还没读码，可能是什么问题？”
- “这个原因的可能性高不高？”

### 2.2 链路调用
- DTC Grouping 已完成，需针对某个 DTC Group 拉取并排序候选原因
- DTC Grouping 输出 independent DTC，需按 single DTC 拉取并排序
- 当前任务中仅存在单个 DTC，需直接按 single DTC 分析
- 用户明确选择某个 DTC 或 DTC Group 继续分析
- 用户仅提供故障现象且当前没有可用 DTC，需基于 symptom_case 分析
- 用户已读码但无 DTC，需基于故障现象进行原因排序
- 用户未提供读码结果，需先提示读码，同时可输出低置信度初步原因方向
- Diagnostic Planning 需要基于候选原因排序结果生成诊断检查计划
- 用户补充症状、检测结果、数据流或维修反馈后，需更新当前分析对象下的原因排序
- Diagnostic Planning 判断当前检查结果影响某些候选原因优先级，需更新排序

## 3. 输入信息

Cause Ranking 根据 `operation` 区分内部子能力：

| operation | 含义 |
|-----------|------|
| `retrieve_causes` | 候选原因拉取 |
| `rank_causes` | 候选原因排序 |

`operation` 是内部执行指令，不代表对外输出拆成两类。对外最终输出仍然是排序后的候选原因列表。

### 3.1 分析对象与 dtc_result

| target_type | 含义 |
|-------------|------|
| `dtc_group` | 多个 DTC 组成的分析对象 |
| `single_dtc` | 一个独立 DTC 分析对象 |
| `symptom_case` | 当前没有可用 DTC 作为分析锚点，基于故障现象分析 |

`symptom_case` 不等于 `no_dtc`。它表示当前分析入口是故障现象，且当前没有可用 DTC 作为分析锚点。若后续读取到 DTC，应转入 `single_dtc` 或 `dtc_group`；故障现象不再作为分析对象本身，而作为排序证据参与 `rank_causes`。

`dtc_result`（仅 symptom_case 必填）：

| 值 | 含义 | 处理原则 |
|----|------|----------|
| `unknown` | DTC 结果未知 | 可低置信度预分析，优先建议读码；不得表达为无 DTC |
| `no_dtc` | 已读码，无 DTC | 可基于故障现象拉取并排序候选原因 |

核心原则：**有没有读取 DTC 是动作；有没有 DTC 是结果。** 有 DTC 时以 DTC 为分析锚点；无 DTC 或 DTC 结果未知时，才以故障现象作为分析入口。

### 3.2 retrieve_causes 输入

| 字段 | 必要性 | 说明 |
|------|--------|------|
| operation | 必备 | `retrieve_causes` |
| target_type | 必备 | `dtc_group` / `single_dtc` / `symptom_case` |
| group_id | 条件必备 | target_type = `dtc_group` 时必填 |
| dtcs | 条件必备 | target_type = `dtc_group` / `single_dtc` 时必填 |
| symptom_description | 条件必备 | target_type = `symptom_case` 时必填 |
| dtc_result | 条件必备 | target_type = `symptom_case` 时必填 |
| brand | 条件必备 | 限定品牌语义与原因数据匹配口径 |
| system | 条件必备 | DTC 场景通常必备；symptom_case 下能识别时输出 |
| related_parts | 可选 | 相关零件，用于拉取与零件相关的候选原因 |
| vehicle_info | 可选 | 车型、年款、VIN、发动机、配置等 |

拉取逻辑：
- DTC 场景：`品牌 + DTC + 系统 + 相关零件`
- symptom_case 场景：`品牌 + 故障现象 + 系统 + 相关零件`
- 数据流、检查结果、维修反馈等主要用于后续排序，不作为拉取的核心输入
- 不得仅基于零件名称拉取泛化原因，也不得跨分析对象拉取无关原因

### 3.3 rank_causes 输入

在 retrieve_causes 输入基础上，增加：

| 字段 | 必要性 | 说明 |
|------|--------|------|
| operation | 必备 | `rank_causes` |
| candidate_causes | 必备 | retrieve_causes 拉取到的候选原因集合 |
| datastreams | 可选 | 实测数据流，用于判断候选原因与车辆状态是否一致 |
| freeze_frame | 可选 | 故障发生时的车辆状态 |
| inspection_results | 可选 | 检查结果，用于更新排序 |
| repair_feedback | 可选 | 已执行维修及维修后结果 |
| recurrence_result | 可选 | 清码、路试、复扫后的故障复现情况 |
| ranked_causes | 可选 | 有新增证据时，作为排序更新基础 |

首次排序：`retrieve_causes` → `rank_causes`。  
后续有新证据时，通常复用已有 `candidate_causes`，仅执行 `rank_causes`。  
用户只是查看步骤、展开分支、浏览维修建议，或只是问“还有别的吗”但未补充新诊断证据时，**不需要**触发排序更新。

## 4. 处理规则

### 4.1 单次仅处理一个分析对象

单次执行范围限定为一个分析对象（一个 DTC Group、一个 single DTC 或一个 symptom_case）。  
存在多个 DTC Group、多个 independent DTC 或多个故障现象对象时，不默认一次性处理所有对象；Repair Agent 应根据诊断优先级、用户选择或交互入口，选择一个分析对象调用 Cause Ranking。

### 4.2 retrieve_causes 场景规则

#### dtc_group
- 仅基于 `品牌 + DTC Group 内 DTC + 系统 + 相关零件` 从**结构化原因数据**拉取
- **不**调用原厂文档检索生成候选原因
- **不**调用大模型生成候选原因
- 若无匹配结果，输出原因数据缺失或无法稳定拉取
- 组内多个 DTC 命中同一标准原因时，在本次结果中聚合展示

#### single_dtc
- 优先从结构化原因数据拉取
- 结构化数据无匹配时，可检索原厂维修资料、诊断手册或维修文档
- 原厂文档有稳定依据时，标记 `cause_source = retrieved_oem_document`
- 结构化数据与原厂文档均无稳定命中时，可调用大模型生成低置信度候选原因
- 大模型兜底必须：`cause_source = llm_generated`、`temporary_cause_id` 必填、`confidence = low`、`uncertainty_note` 必填

#### symptom_case
- `dtc_result = unknown`：优先建议读码；可输出低置信度初步方向；不得表达为无 DTC 或最终根因
- `dtc_result = no_dtc`：可基于故障现象、品牌、系统、相关零件和案例/工单数据拉取；优先结构化症状-原因数据，不足时检索原厂文档，仍无稳定依据时大模型低置信度兜底
- 后续读取到 DTC 时，转入 `single_dtc` 或 `dtc_group`；故障现象转为 rank_causes 的排序证据

### 4.3 聚合同一标准原因

DTC Group 场景下，组内多个 DTC 命中同一标准原因时：
- 合并为一个候选原因
- 保留支持该原因的 DTC 列表和相关零件
- 不重复输出相同标准原因
- 不将不同标准原因强行合并

原因名称标准化、原因编码、同义原因归并和基础去重由数据层完成。

### 4.4 rank_causes 排序规则

基于 `candidate_causes` 和当前可用证据排序。参考因素包括：
- 候选原因来源
- 是否被 DTC Group 内多个 DTC 共同命中
- 是否与 DTC 或故障现象匹配
- 是否与数据流、冻结帧或检查结果匹配
- 是否与相关零件匹配
- 是否在品牌/车型/系统资料中被列为高频原因
- 是否在案例或工单数据中出现频率较高
- 是否已被检查结果或维修反馈影响
- 是否存在资料缺失或上下文不足导致的不确定性
- 是否涉及安全风险或车辆可行驶性

排序变化通过 `ranked_causes` 顺序和 `ranking_basis` 表达，不额外输出证据影响状态。  
可使用大模型辅助排序依据解释，但**不得**新增候选原因、确认最终根因、建议更换零部件或生成诊断检查项。

除非分析对象、DTC 集合、故障现象、品牌、系统或相关零件发生变化，新增证据场景通常不需要重新执行 `retrieve_causes`。

## 5. Tool 使用

优先通过全局工具服务完成候选原因拉取与排序。

### Tool 契约
- Tool 名称：`cause_ranking_service`
- 作用：查询结构化原因数据、检索原厂文档、检索案例数据，并完成候选原因拉取与排序
- 输入：见 `tool-schema.json`；通过 `operation` 区分 `retrieve_causes` 与 `rank_causes`
- 输出：`retrieve_causes` 返回 `candidate_causes`；`rank_causes` 返回 `ranking_result`（含 `ranked_causes`）

### 兜底策略

| 场景 | 降级顺序 |
|------|----------|
| dtc_group | 仅结构化原因数据；未命中时不使用原厂文档或大模型补原因 |
| single_dtc | 结构化原因数据 → 原厂文档检索 → 大模型低置信度兜底 |
| symptom_case | 根据 dtc_result 判断；unknown 时优先建议读码 + 低置信度预分析；no_dtc 时结构化数据 → 原厂文档 → 大模型兜底 |

大模型兜底原因必须标记 `cause_source = llm_generated` 且 `confidence = low`，不得伪装为结构化原因数据或原厂文档依据。

## 6. 输出结构

核心输出为 `ranking_result` + `ranked_causes`。数组顺序代表候选原因优先级。

### 6.1 顶层字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| ranking_result | 必备 | 本次 Cause Ranking 的整体排序结果；信息不足时为 null |
| uncertainty_note | 条件必备 | 信息不足、低置信度、证据冲突或大模型兜底时输出 |
| missing_required_info | 条件必备 | 无法完成拉取或排序时输出缺失信息 |

`ranking_result` 内字段：

| 字段 | 必要性 | 说明 |
|------|--------|------|
| target_type | 必备 | `dtc_group` / `single_dtc` / `symptom_case` |
| group_id | 条件必备 | DTC Group 时输出 |
| dtc_result | 条件必备 | symptom_case 时输出 |
| dtcs | 条件必备 | DTC 场景输出；symptom_case 可为空 |
| symptom_description | 条件必备 | symptom_case 时输出 |
| system | 条件必备 | 能识别所属系统时输出 |
| ranked_causes | 必备 | 排序后的候选原因列表 |
| uncertainty_note | 条件必备 | 整体不确定性说明 |

### 6.2 ranked_causes 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| cause_id | 条件必备 | 结构化原因命中时输出 |
| temporary_cause_id | 条件必备 | 大模型兜底且无稳定 cause_id 时输出 |
| cause_name | 必备 | 候选原因名称 |
| cause_source | 必备 | `structured_reason_data` / `retrieved_oem_document` / `llm_generated` |
| source_reference | 可选 | 结构化记录 ID、原厂文档 ID、知识库 chunk ID、案例 ID 等 |
| supported_dtcs | 条件必备 | 当前分析对象存在 DTC 时，说明该原因由哪些 DTC 支撑 |
| related_parts | 可选 | 该原因涉及的相关零件 |
| priority | 必备 | `high` / `medium` / `low` |
| confidence | 必备 | `high` / `medium` / `low`；大模型兜底必须为 `low` |
| ranking_basis | 必备 | 排序依据说明 |
| uncertainty_note | 条件必备 | 证据不足、冲突、低置信度或大模型兜底时输出 |

字段边界：
- `priority = high` 不代表最终根因
- `confidence = low` 不代表已排除
- DTC Group 场景下候选原因必须来自结构化原因数据

### 6.3 输出示例

**DTC Group 正常输出：**

```json
{
  "ranking_result": {
    "target_type": "dtc_group",
    "group_id": "G1",
    "dtcs": ["P0420", "P0430"],
    "system": "发动机系统 / 排放系统",
    "ranked_causes": [
      {
        "cause_id": "CAUSE_EMISSION_001",
        "cause_name": "催化转换器效率下降",
        "cause_source": "structured_reason_data",
        "source_reference": "DTC2FIX_CAUSE_001",
        "supported_dtcs": ["P0420", "P0430"],
        "related_parts": ["催化转换器", "排气系统"],
        "priority": "high",
        "confidence": "medium",
        "ranking_basis": [
          "P0420 / P0430 均与催化转换器效率低相关",
          "该候选原因被组内多个 DTC 共同命中",
          "当前故障组相关零件包含催化转换器"
        ]
      }
    ]
  }
}
```

**symptom_case（dtc_result = unknown）：**

```json
{
  "ranking_result": {
    "target_type": "symptom_case",
    "dtc_result": "unknown",
    "dtcs": [],
    "symptom_description": "车辆冷启动困难，偶尔需要多次启动，暂未提供故障码读取结果。",
    "system": "发动机系统",
    "ranked_causes": [
      {
        "temporary_cause_id": "LLM_CAUSE_001",
        "cause_name": "燃油压力不足",
        "cause_source": "llm_generated",
        "related_parts": ["燃油泵", "燃油滤清器", "燃油压力调节相关部件"],
        "priority": "medium",
        "confidence": "low",
        "ranking_basis": [
          "当前 DTC 结果未知，缺少关键诊断证据",
          "冷启动困难与燃油压力不足方向存在相关性",
          "该候选原因仅作为初步排查方向"
        ],
        "uncertainty_note": "当前未获取 DTC 结果，建议优先进行全车扫描。若读取到 DTC，应转入 single_dtc 或 dtc_group 场景重新分析。"
      }
    ],
    "uncertainty_note": "当前为 DTC 结果未知的故障现象场景，建议优先读取 DTC 后再进行更稳定的原因排序。"
  }
}
```

**信息不足：**

```json
{
  "ranking_result": null,
  "uncertainty_note": "当前缺少可用于候选原因拉取和排序的关键上下文，暂无法稳定生成候选原因排序。",
  "missing_required_info": [
    "当前分析对象",
    "品牌",
    "系统",
    "DTC 或故障现象描述"
  ]
}
```

## 7. 边界规则

该 Skill **负责**：
- 针对当前分析对象拉取候选原因
- 支持 dtc_group、single_dtc、symptom_case 三类分析对象
- 聚合同一分析对象下重复命中的标准原因
- 基于候选原因和当前证据进行排序
- 在新增诊断证据出现后更新候选原因排序
- 输出排序后的候选原因、优先级、置信度、排序依据和不确定性说明
- 为 Diagnostic Planning 提供排序后的候选原因输入

该 Skill **不负责**：
- 生成诊断检查项、诊断检查路径、维修方案、具体维修步骤
- 直接给出零部件更换建议或最终根因判断

Diagnostic Planning 可基于以下字段继续生成检查计划：
- `ranked_causes`
- `cause_id` / `temporary_cause_id`
- `dtcs`
- `symptom_description`
- `dtc_result`
- `system`
- `related_parts`

## 8. 异常与兜底

兜底重点：**不因数据缺失而编造高置信度原因，不因排序靠前而表达为最终根因。**

以下情况进入异常或兜底处理：
- 当前分析对象不明确
- 品牌、系统、DTC 或故障现象缺失
- symptom_case 下缺少 dtc_result
- 候选原因数据无匹配结果
- 候选原因为空，无法进入排序
- 新增证据与已有信息冲突
- 涉及制动、转向、安全气囊、高压系统等高风险系统且证据不足

处理原则：
- 能补全信息则优先补全
- 无法稳定判断时不输出确定性结论
- 涉及高风险系统时，应提示风险并建议人工确认

## 9. 验收标准

- 能正确识别分析对象为 `dtc_group`、`single_dtc` 或 `symptom_case`；independent DTC 按 `single_dtc` 处理
- 能区分 symptom_case 下 `dtc_result = unknown` 与 `no_dtc`，unknown 时不得表达为无 DTC
- DTC Group 场景只从结构化原因数据拉取；single_dtc 和 symptom_case 按降级顺序处理
- 能正确标记 `structured_reason_data`、`retrieved_oem_document`、`llm_generated`
- 排序结果通过 `ranking_basis` 可解释，不得表达为最终根因确认
- 用户补充新证据后能基于已有候选原因更新排序
- 输出结果可被 Diagnostic Planning 衔接使用
