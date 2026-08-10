---
name: dtc-grouping
description: 对多个 DTC 进行聚合分析，优先按品牌、系统、相关零件将故障码组织成可联合分析的 DTC Group 或 independent DTC，为 Cause Ranking 和 Diagnostic Planning 提供结构化输入。该 Skill 负责组织分析对象，不判断故障原因或输出维修方案。
tools:
  - global_tool: dtc_grouping_service
    description: 基于 DTC 所属系统、相关零件及结构化分组数据，将多个 DTC 组织为 DTC Group 或 independent DTC。
    required: true
---

# DTC Grouping Skill

## 1. 目标

该 Skill 负责对多个 DTC 进行聚合分析，优先按照**品牌、系统、相关零件**将多个故障码组织成可联合分析的 DTC Group 或 independent DTC，为后续 Cause Ranking 和 Diagnostic Planning 提供结构化输入。

它主要回答：
- 多个 DTC 是否应放在同一系统、同一相关零件范围下进行联合分析？
- 为什么这样分组？

核心链路：

```
多个 DTC 输入
  ↓
按品牌 / 系统 / 相关零件划定分析对象
  ↓
生成 DTC Group / independent DTC
  ↓
输出分组依据与分组置信度
```

说明：
- DTC Grouping 用于避免 Repair Agent 对多个 DTC 逐个孤立分析，帮助系统先将多个故障码组织成可联合分析的对象。
- 分组时优先按**系统**划定边界，并在同一系统内通过**相关零件**进行桥接分组；跨系统 DTC 默认不强行合并。
- DTC Grouping 的输出仅作为后续 Cause Ranking 和 Diagnostic Planning 的结构化输入，**不作为最终诊断结论**。
- 同组 DTC 仅表示这些 DTC 适合放在同一个分析对象下联合分析，**不代表**已经确认它们由同一个根因导致。

## 2. 触发条件

在以下场景中使用该 Skill：

### 2.1 用户明确提问
- “宝马同时报 P0171 和 P0300，怎么排查？”
- “这几个故障码有没有关系？”
- “这些故障码哪个要先处理？”
- “为什么发动机和变速箱都报故障？”
- “清码后又出现这些故障码，是同一个问题吗？”
- “这些 DTC 能不能一起排查？”

### 2.2 链路调用
- 当前任务中存在多个 DTC
- Diagnosis Context 中存在多个当前 DTC
- 诊断报告中包含多个系统或多个 DTC
- Repair Agent 判断当前问题属于多 DTC 联合分析场景
- Cause Ranking 需要基于 DTC 分组结果生成候选原因
- Diagnostic Planning 需要基于故障组结果生成分组化检查计划
- 用户上传新的诊断报告，DTC 列表发生变化
- 用户补充新的 DTC 后，当前 DTC 集合发生变化
- 清码后多个 DTC 再次复现，需要重新判断分组

**若当前任务中仅存在单个 DTC，不应触发 DTC Grouping，应直接进入单 DTC 分析链路。**

## 3. 输入信息

### 核心输入

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| dtc_list | 当前 DTC 列表 | 必备 | 当前需要分组的多个 DTC，来自用户输入、诊断报告、诊断设备检测等 |
| brand | 品牌 | 必备 | 用于统一品牌语义、DTC 解释口径和零件映射口径 |
| dtc_entries | DTC 明细 | 必备 | 每个 DTC 的所属系统和相关零件，与 dtc_list 一一对应 |
| vehicle_info | 车辆信息 | 可选 | 车型、年款、VIN、发动机、已知配置等，用于提高分组精度和辅助消歧 |

`dtc_entries` 中每个条目包含：

| 字段 | 必要性 | 说明 |
|------|--------|------|
| dtc_code | 必备 | DTC 编码 |
| system | 必备 | 该 DTC 所属系统，用于按系统划定一级分组边界 |
| related_parts | 必备 | 该 DTC 涉及的相关零件 / 部件，用于同一系统内桥接分组 |

说明：
- `system` 和 `related_parts` 应与具体 DTC 对应，系统基于每个 DTC 的所属系统和相关零件完成分组。
- DTC Grouping 执行前必须具备 `dtc_list`、`brand`，以及每个 DTC 的 `system` 和 `related_parts`。
- 这些信息不一定由用户直接提供，可以由诊断报告、DTC 数据库、结构化数据服务、当前 Diagnosis Context 或 DTC Context Skill 补全。
- 若补全后仍缺少品牌、DTC 所属系统或相关零件，则不应强行分组；系统应提示缺失信息，或将无法稳定分析的 DTC 按 independent DTC 处理。

## 4. 处理规则

### 4.1 前置条件判断

DTC Grouping 执行前应确认：
- 当前任务中存在**多个 DTC**
- 已具备品牌、每个 DTC 的所属系统和相关零件信息

若仅存在单个 DTC，不触发 DTC Grouping。  
若品牌、DTC 所属系统或相关零件缺失，应优先通过诊断报告、DTC 数据库、结构化数据服务或 DTC Context Skill 补全；补全后仍缺失时，不强行分组。

### 4.2 按系统和相关零件进行分组

DTC Grouping 应先基于 DTC 所属**系统**划定分析边界，再在同一系统内通过**相关零件**进行桥接分组。

基本规则：

```
多个 DTC
+ 同一品牌
+ 同一系统
+ 相关零件存在交集或高度相关
  ↓
形成 DTC Group
```

相关零件包括：零件、相关配件、线路、模块、传感器、执行器、连接器。

当多个 DTC 指向相同或高度相关的零件 / 部件时，系统可将其归为同一 DTC Group，作为后续 Cause Ranking 和 Diagnostic Planning 的联合分析对象。

DTC 语义、检测对象和故障方向可用于辅助说明 `grouping_basis`，但不作为独立于品牌、系统和相关零件之外的主分组轴。

同一 DTC Group 仅表示这些 DTC 可通过相关零件建立分析关联，**不代表**已经确认该零件为最终故障原因。

### 4.3 跨系统 DTC 处理

当多个 DTC 分属不同系统时，DTC Grouping **默认不将其合并**为同一 DTC Group，也不进行零件级桥接。

跨系统 DTC 是否存在共同原因，不在 DTC Grouping 阶段判断，应交由后续 Cause Ranking 或 Diagnostic Planning 在结合症状、检测结果、数据流、冻结帧和检查结果后进一步判断。

DTC Grouping 可以输出 `uncertainty_note`，提示当前存在跨系统 DTC，后续需要结合更多证据判断是否存在共同原因。

### 4.4 无法稳定分组时按 independent DTC 处理

当系统缺少稳定分组依据时，**不调用大模型进行兜底分组**，也不生成低置信度 DTC Group。

无法稳定分组的 DTC 应进入 `independent_dtcs`，分别进入后续 Cause Ranking 分析。

以下情况应按 independent DTC 处理：
- 缺少 DTC 所属系统，且无法补全
- 缺少相关零件，且无法补全
- 多个 DTC 分属不同系统，且无法在同一系统内形成稳定分组
- 相关零件不存在交集或高度相关关系
- DTC 分组工具不可用、返回为空或结果不稳定
- 数据来源存在冲突，无法确认当前有效分组依据

核心原则：**DTC Grouping 不做猜测式分组。无法稳定分组时，按 independent DTC 处理。**

## 5. Tool 使用

优先通过全局工具服务完成 DTC 分组。

### Tool 契约
- Tool 名称：`dtc_grouping_service`
- 作用：基于 DTC 所属系统、相关零件及结构化分组数据，将多个 DTC 组织为 DTC Group 或 independent DTC
- 输入：`dtc_list`、`brand`、`dtc_entries`、`vehicle_info`
- 输出：标准化的 DTC Grouping 结果对象

### 兜底策略

DTC Grouping 的兜底原则是：**不做猜测式分组。无法稳定分组时，按 independent DTC 处理。**

以下情况不应强行生成 DTC Group：
- 缺少品牌、DTC 所属系统或相关零件，且无法补全
- DTC 分组工具不可用、返回为空或结果不稳定
- 多个 DTC 分属不同系统，且无法在同一系统内形成稳定分组
- 相关零件不存在交集或高度相关关系
- 用户输入、诊断报告或数据来源之间存在冲突

处理方式：
- 可补全的信息优先补全
- 无法补全或无法稳定分组时，放入 `independent_dtcs`
- 跨系统 DTC 默认不强行合并
- **不调用大模型进行兜底分组**
- 涉及制动、转向、安全气囊、高压系统等高风险系统且无法稳定分组时，可提示人工确认

## 6. 输出结构

该 Skill 必须返回如下标准化对象：

```json
{
  "dtc_groups": [
    {
      "group_id": "G1",
      "group_name": "空气流量传感器、氧传感器故障零部件组",
      "representative_dtc": "P0171",
      "dtc_codes": ["P0171", "P0300"],
      "dtcs": ["P0171", "P0300"],
      "record_ids": [101, 102],
      "group_names": ["空气流量传感器", "氧传感器"],
      "dtc_category": "动力系统",
      "system": "发动机系统",
      "group_reason": "same_system_shared_parts",
      "member_count": 2,
      "related_parts": [
        "MAF 空气流量传感器",
        "氧传感器",
        "真空管路",
        "进气管路"
      ],
      "grouping_basis": [
        "多个 DTC 属于发动机系统",
        "多个 DTC 可通过进气、空气流量和燃烧控制相关零件建立分析关联",
        "DTC 语义均与发动机燃烧异常方向相关"
      ],
      "grouping_confidence": "high"
    },
    {
      "group_id": "G2",
      "group_name": "CAN 通信线路、控制模块故障零部件组",
      "representative_dtc": "U0100",
      "dtc_codes": ["U0100", "U0121"],
      "dtcs": ["U0100", "U0121"],
      "record_ids": [201, 202],
      "group_names": ["CAN 通信线路", "控制模块"],
      "dtc_category": "网络通讯系统",
      "system": "车身网络 / 通信系统",
      "group_reason": "same_system_shared_parts",
      "member_count": 2,
      "related_parts": ["CAN 通信线路", "控制模块"],
      "grouping_basis": [
        "多个 DTC 属于通信类故障",
        "多个 DTC 可通过 CAN 通信线路或控制模块通信关系建立分析关联"
      ],
      "grouping_confidence": "high"
    }
  ],
  "independent_dtcs": ["B1234"]
}
```

### 6.1 顶层输出字段

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| dtc_groups | DTC 分组列表 | 必备 | 可联合分析的 DTC 分组列表；无法稳定分组时为空数组 |
| independent_dtcs | 独立 DTC 列表 | 必备 | 未能稳定归入任何 DTC Group、需独立分析的 DTC 列表；可为空数组 |
| grouping_result | 分组结果说明 | 条件必备 | 无法稳定分组、信息不足或异常场景下输出 |
| uncertainty_note | 不确定性说明 | 条件必备 | 跨系统、资料缺失、数据冲突或无法稳定分组时输出 |
| missing_required_info | 缺失必要信息 | 条件必备 | 当前无法完成稳定分组时，需要补充的信息 |

### 6.2 DTC Group 内部字段

当 `dtc_groups` 中存在分组时，每个 DTC Group 应包含以下字段：

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| group_id | 分组 ID | 必备 | 当前 DTC Group 的唯一标识（与 /api/v1/dtc-groups 口径一致） |
| group_name | 分组名称 | 必备（已废弃） | 中台兼容组名；新调用方优先使用 `group_names` |
| representative_dtc | 代表 DTC | 必备 | 组内出现频次最高的故障码 |
| dtc_codes | 组内 DTC 列表 | 必备 | 当前 DTC Group 包含的 DTC 列表（去重排序） |
| dtcs | 组内 DTC 列表 | 必备（已废弃） | 中台兼容字段，值同 `dtc_codes`；新调用方优先使用 `dtc_codes` |
| record_ids | 知识记录 ID 列表 | 必备 | 组内成员对应的知识记录 ID；无记录 ID 时可为空数组 |
| group_names | 组名来源零件列表 | 必备 | 组内各逻辑 DTC 共享的规范化零部件（交集） |
| dtc_category | PCBU 一级分类 | 必备 | `动力系统` / `底盘系统` / `车身系统` / `网络通讯系统`，无法判定时为 null |
| system | 所属二级系统 | 可选 | 组内成员系统一致时为该系统名；跨系统聚类时为 null |
| group_reason | 分组原因 | 必备 | 机器枚举：`same_code` / `same_system_shared_parts` / `shared_parts` / `standalone` |
| member_count | 成员数 | 必备 | 组内成员记录条数 |
| related_parts | 相关零件 | 必备 | 当前 DTC Group 涉及的相关零件 / 部件（成员并集） |
| grouping_basis | 分组依据 | 必备 | 说明为什么这些 DTC 被归为同一组 |
| grouping_confidence | 分组置信度 | 必备 | 当前分组结果的可信程度：`high` / `medium` |

说明：
- `dtc_groups` 为空时，不需要输出 `group_id` 等组内字段
- `dtc_groups` 不为空时，除 `system`（跨系统聚类时为 null）外，每个 group 内部字段均为必备
- `group_name`、`dtcs` 为面向旧调用方的兼容字段，取值分别由 `group_names`、`dtc_codes` 派生
- `grouping_basis` 不得表达为根因判断

### 6.3 无法稳定分组输出示例

```json
{
  "dtc_groups": [],
  "independent_dtcs": ["P0171", "U0100", "B1234"],
  "grouping_result": "无法稳定将多个 DTC 归入同一系统或通过相关零件建立稳定分析关联，建议按 independent DTC 分别分析。"
}
```

### 6.4 信息不足输出示例

```json
{
  "dtc_groups": [],
  "independent_dtcs": [],
  "grouping_result": "当前信息不足，暂无法稳定完成 DTC 分组。",
  "missing_required_info": [
    "品牌",
    "DTC 所属系统",
    "相关零件"
  ]
}
```

## 7. 边界规则

该 Skill **负责**：
- 接收多个 DTC
- 判断当前 DTC 集合是否需要分组
- 基于品牌、系统和相关零件划定分析对象
- 将多个 DTC 组织为一个或多个 DTC Group
- 将无法稳定归组的 DTC 标记为 independent DTC
- 输出分组依据和分组置信度
- 为 Cause Ranking 和 Diagnostic Planning 提供结构化输入

该 Skill **不负责**：
- 判断故障原因、主次故障或 DTC 之间的因果关系
- 输出候选原因、诊断检查项或维修方案

核心边界：DTC Grouping 的职责是**组织分析对象**，不是构建原因空间。

Cause Ranking 和 Diagnostic Planning 可基于以下字段继续分析：
- `dtc_groups`（含 `group_id`、`dtc_codes`、`system`、`related_parts`）
- `independent_dtcs`

## 8. 异常与兜底

兜底重点：**不做猜测式分组。无法稳定分组时，按 independent DTC 处理。**

出现以下情况时，不应强行生成 DTC Group：
- 缺少品牌、DTC 所属系统或相关零件，且无法补全
- DTC 分组工具不可用、返回为空或结果不稳定
- 多个 DTC 分属不同系统，且无法在同一系统内形成稳定分组
- 相关零件不存在交集或高度相关关系
- 用户输入、诊断报告或数据来源之间存在冲突，无法确认当前有效 DTC 列表或分组依据

处理原则：
- 能补全的信息优先补全
- 无法补全或无法稳定分组时，放入 `independent_dtcs`
- 跨系统 DTC 默认不强行合并
- 不调用大模型进行兜底分组
- 涉及制动、转向、安全气囊、高压系统等高风险系统且无法稳定分组时，可提示人工确认

## 9. 验收标准

- 多个 DTC 场景能正确触发 DTC Grouping；单 DTC 场景不触发
- 执行分组前必须具备当前 DTC 列表、品牌、每个 DTC 的所属系统和相关零件
- 能够基于同一品牌、同一系统、相关零件交集或高度相关性生成 DTC Group
- 跨系统 DTC 不强行合并；无法稳定分组时进入 `independent_dtcs`
- 每个 DTC Group 应输出明确的 `grouping_basis`，但不得表达为根因判断
- 不输出候选原因、根因判断、主次故障判断、诊断检查项或维修方案
- 输出结果应可作为 Cause Ranking 和 Diagnostic Planning 的结构化输入
