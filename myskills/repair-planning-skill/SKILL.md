---
name: repair-planning
description: 基于明确的 repair_target，从结构化维修知识中查询维修方案，并组织维修方法、零部件、可选工时价格和维修后验证建议。该 Skill 只在维修目标明确后回答"怎么修"，不负责诊断确认或执行维修动作。
tools:
  - global_tool: repair_planning_service
    description: 基于 repair_target 和品牌/车辆上下文，从结构化维修知识中查询维修方案、维修方法、零件、工时和价格，输出 repair_plan。
    required: true
---

# Repair Planning Skill

## 1. 目标

该 Skill 负责基于明确的 `repair_target`，从结构化维修知识中查询维修方案，并组织维修方法、零部件、可选工时价格和维修后验证建议。

它主要回答：
- 维修目标明确后，对应哪个维修方案？
- 具体怎么修？
- 涉及哪些零部件？
- 需要多少工时、价格如何？（可选）
- 修完后怎么验证？

核心链路：

```
repair_target + 品牌 / 车辆信息 / DTC 或故障现象 / 系统 / 相关零件
  ↓
查询结构化维修知识
  ↓
获取维修方案、维修方法、零部件、工时、价格
  ↓
组织 repair_plan
  ↓
输出维修后验证建议
```

在 Repair Agent 主链路中，Repair Planning 位于 Diagnostic Planning 之后：

**有 DTC 场景：**
```
DTC Context → DTC Grouping → Cause Ranking → Diagnostic Planning → Repair Planning
```

**无可用 DTC 的 symptom_case 场景：**
```
Cause Ranking → Diagnostic Planning → Repair Planning
```

说明：
- `repair_target` 是核心输入，表示当前明确的维修目标
- `repair_plan` 是核心输出
- Repair Planning 不关心最初入口是 DTC Group、single DTC 还是 symptom_case，只关心当前是否已经形成明确的 `repair_target`

## 2. 触发条件

### 2.1 用户明确提问
- “已经确认是进气泄漏，怎么修？”
- “氧传感器坏了怎么修？”
- “节气门坏了怎么处理？”
- “喷油嘴堵塞怎么维修？”
- “如果是 MAF 传感器故障，维修方案是什么？”
- “这个零件坏了需要更换还是维修？”
- “修完后怎么确认修好了？”
- “这个维修大概要多少钱？”
- “这个维修大概要多久？”

当用户询问故障假设或用户指定维修对象时，可生成**条件性维修方案**，但必须说明：该维修方案表示 `repair_target` 成立时的处理方式，不代表当前车辆故障原因已经确认。

### 2.2 链路调用
- Diagnostic Planning 输出 `confirmed_cause`
- Diagnostic Planning 输出 `next_action = enter_repair_planning`
- 当前任务状态已进入维修方案规划阶段
- 用户要求基于已确认原因生成维修方案
- 用户要求了解维修方案、维修方法、所需零件、工具、风险提示或维修后验证
- 用户要求同时了解维修工时或价格

**不应自动触发的情况：**
- 当前只有 Cause Ranking 的候选原因排序，但原因尚未确认
- 用户没有明确指定维修对象、零件故障或故障假设
- 当前任务仍处于诊断检查阶段
- 检查结果不足以确认维修目标

核心原则：**不能因为某个候选原因排名靠前，就自动进入维修方案或换件建议。**

## 3. 输入信息

| 字段 | 必要性 | 说明 |
|------|--------|------|
| repair_target | 必备 | 本次维修方案的查询对象 |
| brand | 条件必备 | 用于匹配品牌相关维修方案、零件、工时和价格 |
| vehicle_info | 可选 | 车型、年款、VIN、发动机、配置等 |
| target_type | 可选 | `dtc_group` / `single_dtc` / `symptom_case` / `user_specified_target` |
| dtcs | 条件必备 | 当前维修目标关联的 DTC |
| symptom_description | 条件必备 | 当前维修目标来自 symptom_case 时携带 |
| dtc_result | 条件必备 | symptom_case 时携带（`unknown` / `no_dtc`） |
| group_id | 条件必备 | 当前维修目标来自 DTC Group 时携带 |
| system | 条件必备 | 当前维修目标所属系统 |
| related_parts | 条件必备 | 当前维修目标涉及的相关对象 |
| output_options | 可选 | 控制是否输出工时和价格，默认 `include_labor_price = false` |

说明：
- 结构化维修知识不作为输入字段，而是数据源 / 工具依赖
- `confirmed_cause`、用户指定故障假设、用户指定零件故障或用户指定维修对象，都可以形成 `repair_target`
- **未确认的候选原因不能自动转化为 repair_target**

### 3.1 repair_target 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| target_name | 必备 | 例如“进气泄漏”“氧传感器损坏”“节气门积碳” |
| target_status | 必备 | `confirmed` / `user_hypothesis` / `user_specified_object` |
| target_description | 可选 | 对维修目标的补充说明 |
| cause_id | 条件必备 | 来源于已确认原因或标准原因数据时输出 |
| related_parts | 可选 | 该维修目标涉及的零件、部件或相关对象 |
| source | 可选 | Diagnostic Planning / 用户输入 / 当前任务状态 |

`target_status` 说明：

| 枚举值 | 说明 |
|--------|------|
| confirmed | 来自 Diagnostic Planning 的确认结果 |
| user_hypothesis | 用户询问“如果是某原因，该怎么修” |
| user_specified_object | 用户直接指定某个零件、部件或维修对象 |

### 3.2 output_options 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| include_labor_price | 可选 | `true` / `false`；默认 `false` |

说明：
- 默认输出维修方案、维修方法、零部件和维修后验证建议
- 工时和价格属于可选输出内容
- 当 `include_labor_price = true` 时，才尝试输出工时和价格
- 缺少结构化工时或价格数据时，可以低置信度兜底估算，但必须标记来源、置信度和不确定性

## 4. 处理规则

### 4.1 主流程

```
repair_target 明确
  ↓
查询结构化维修知识
  ↓
获取维修方案、维修方法、零部件、工时和价格
  ↓
组织 repair_plan
  ↓
输出维修后验证建议
```

- Repair Planning **不确认原因**，只基于明确维修目标组织维修方案和维修方法
- 查询维修方案是内部处理步骤，不作为独立对外子能力
- `repair_plan` 是对外核心输出

### 4.2 查询维修方案

Repair Planning 必须基于明确的 `repair_target` 查询维修方案。

```
repair_target + 品牌 / 车辆信息 / DTC 或故障现象 / 系统 / 相关零件
  ↓
查询结构化维修知识
  ↓
返回维修方案、维修方法、零部件、工时、价格
```

应优先从结构化维修知识中获取：
- 维修方案（修什么）
- 维修方法（具体怎么修）
- 零件 / 耗材（用什么修）
- 工时、价格（仅 `include_labor_price = true` 时输出）

当 `repair_target` 来自用户假设或用户指定对象时，输出应按“该假设成立时”的条件性维修方案处理，不表达为当前车辆故障原因已经确认。

当结构化维修知识缺失时，可对维修方案、维修方法、工时和价格进行低置信度兜底生成，但必须明确标记来源、置信度和不确定性。

### 4.3 分析对象处理差异

Repair Planning 的核心仍然是 `repair_target`，不同上游分析对象影响查询依据：

**DTC Group 场景：**
- 维修目标通常来自 Diagnostic Planning 的 `confirmed_cause`
- 维修方案应围绕已确认原因展开
- 不应因 DTC Group 中某个候选原因排名高就自动生成维修方案
- 若维修目标只覆盖组内部分 DTC，应在维修后验证中说明需要复扫确认其他 DTC 是否仍存在

**single DTC 场景：**
- 可基于已确认原因或用户明确指定的故障假设生成
- 若原因来自大模型低置信度兜底且未经过 Diagnostic Planning 确认，不应自动进入 Repair Planning
- 用户明确询问“如果是该原因怎么修”时，可以生成条件性维修方案

**symptom_case 场景：**
- 维修方案应更强调不确定性
- 若 `dtc_result = unknown`，原则上应优先建议读码；只有在维修目标已明确或用户指定假设时，才生成维修方案
- 若 `dtc_result = no_dtc`，可基于已确认原因或用户指定对象生成维修方案
- 若后续读取到 DTC，应回到 DTC 驱动链路重新评估
- 大模型兜底维修方案必须低置信度标记，不得表达为确定维修结论

核心原则：**Repair Planning 不以 DTC 或故障现象直接决定怎么修，而是以明确的 repair_target 决定怎么修。**

### 4.4 维修方案与维修方法

| 层级 | 示例 | 回答的问题 |
|------|------|-----------|
| repair_solution（维修方案） | 更换前氧传感器 | 修什么 |
| repair_method（维修方法） | 确认传感器位置后，断开连接器，拆下旧传感器，安装新传感器，清码并复查数据流 | 具体怎么修 |
| parts（零部件） | 前氧传感器、密封垫 | 用什么修 |
| labor_estimate（工时） | 0.5 - 1.5 小时 | 修多久 |
| cost_estimate（价格） | 零件费 + 工时费 | 多少钱 |

说明：
- `repair_method` 不需要过度结构化，可直接用自然语言输出
- 维修方法不等同于完整维修手册
- 维修方法应围绕维修方案展开，不得脱离维修目标生成无关内容
- 高风险维修不应输出面向非专业用户的详细操作指令，应提示由专业技师执行

核心原则：**维修方案回答“修什么”，维修方法回答“具体怎么修”；不得把维修方法混同为维修方案。**

### 4.5 工时和价格输出规则

当 `include_labor_price = true` 时，可输出：
- 工时预估
- 零件价格
- 工时费用
- 总费用或费用区间

输出原则：
- 结构化工时和价格优先使用标准维修数据、历史工单、报价系统或价格库
- 缺少结构化数据时，可以低置信度兜底估算
- 兜底估算必须明确标记来源、置信度和不确定性
- 费用预估应标记为参考值，不作为最终报价
- 当 `include_labor_price = false` 时，可不输出工时和价格

### 4.6 维修后验证建议

`post_repair_validation` 应说明维修后如何确认修好，可包括：
- 是否需要清除 DTC
- 是否需要重新扫描故障码
- 是否需要读取相关数据流
- 是否需要执行主动测试、校准、学习或初始化
- 是否需要路试或复查故障是否复现
- 如果维修后验证失败，应回到 Diagnostic Planning 或 Cause Ranking 继续排查

说明：
- `post_repair_validation` 不需要过度结构化，可直接用自然语言输出
- 维修后验证不是独立 Skill
- symptom_case 场景下，应更强调维修后复查故障现象是否消失

### 4.7 大模型兜底边界

当结构化维修知识缺失、无匹配结果或召回不足时，可调用大模型生成低置信度兜底结果。

可兜底生成：维修方案、维修方法、工时预估、价格预估。

大模型兜底原则：
- 必须标记 `solution_source = llm_generated`
- 置信度默认不得高于 `low`
- 必须输出不确定性说明
- **不得编造**维修方案 ID 或零件编号
- 工时和价格可作为参考估算输出，但必须说明仅供参考
- 高风险维修不得输出详细操作指导，应提示由专业技师处理

## 5. Tool 使用

优先通过全局工具服务完成维修方案查询与组织。

### Tool 契约
- Tool 名称：`repair_planning_service`
- 作用：基于 repair_target 和品牌/车辆上下文，从结构化维修知识中查询并组织维修方案
- 输入：`repair_target`、`brand`、诊断上下文、`output_options`
- 输出：`repair_plan`

### 兜底策略

| 场景 | 处理方式 |
|------|----------|
| 缺少 repair_target | 不生成维修方案，输出 `missing_required_info` |
| 只有候选原因未确认 | 不自动进入 Repair Planning |
| 用户指定假设 | 生成条件性维修方案，标记 `user_hypothesis` |
| 结构化知识未命中 | 大模型低置信度兜底，标记 `llm_generated` |
| 缺少工时/价格数据 | 低置信度估算，标记来源和不确定性 |
| 高风险维修 | 提示由专业技师处理，不输出详细操作指导 |
| symptom_case + dtc_result = unknown | 维修目标不明确时，优先回到诊断链路 |

## 6. 输出结构

核心输出为 `repair_plan`。

### 6.1 顶层输出字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| repair_plan | 条件必备 | 正常生成维修方案时输出；低置信度兜底成功时也可输出 |
| uncertainty_note | 条件必备 | repair_plan 无法生成、整体低置信度或信息不足时输出 |
| missing_required_info | 条件必备 | 无法生成维修方案时输出缺失信息 |

### 6.2 repair_plan 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| repair_target | 必备 | 本次维修方案的查询和生成对象 |
| target_type | 可选 | `dtc_group` / `single_dtc` / `symptom_case` / `user_specified_target` |
| repair_solution | 必备 | 命中的维修方案，回答“修什么” |
| repair_method | 必备 | 用自然语言说明该维修方案大概怎么执行 |
| parts | 可选 | 该维修方案涉及的零件、耗材或替换件 |
| labor_estimate | 条件输出 | `include_labor_price = true` 时输出 |
| cost_estimate | 条件输出 | `include_labor_price = true` 时输出 |
| risk_level | 必备 | `low` / `medium` / `high` |
| warning_note | 条件必备 | 高风险、专用工具、编程、校准、条件性方案等场景输出 |
| post_repair_validation | 必备 | 用自然语言说明维修后如何确认修好 |
| uncertainty_note | 条件必备 | 条件性方案、低置信度、资料不足等场景输出 |

### 6.3 repair_solution 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| repair_solution_id | 条件必备 | 结构化维修方案存在时输出；大模型兜底时不得编造 |
| repair_solution_name | 必备 | 当前维修方案名称 |
| repair_solution_description | 可选 | 对维修方案的补充说明 |
| matched_cause_id | 条件必备 | 对应原因 ID |
| matched_cause_name | 条件必备 | 对应原因名称 |
| matched_dtcs | 可选 | 当前维修方案对应的 DTC |
| matched_symptom | 可选 | 来自 symptom_case 时可输出 |
| solution_source | 必备 | `structured_repair_knowledge` / `llm_generated` |
| source_confidence | 必备 | `high` / `medium` / `low` |
| uncertainty_note | 条件必备 | 方案匹配不确定、低置信度或兜底生成时输出 |

### 6.4 parts 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| part_name | 必备 | 零件、耗材或替换件名称 |
| quantity | 可选 | 所需数量 |
| part_number | 可选 | 有可靠零件数据时输出；**不得编造** |
| part_type | 可选 | `oem` / `brand` / `aftermarket` / `remanufactured` / `used` / `unknown` |
| price_estimate | 条件输出 | `include_labor_price = true` 且存在价格依据时输出 |
| source | 可选 | `structured_repair_knowledge` / `parts_catalog` / `price_database` / `llm_generated` |
| uncertainty_note | 条件必备 | 零件匹配不确定或兜底生成时输出 |

### 6.5 labor_estimate 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| estimated_time | 必备 | 例如 0.5 - 1.5 小时 |
| source | 条件必备 | `labor_database` / `standard_repair_data` / `case_work_order` / `llm_generated` |
| source_confidence | 必备 | `high` / `medium` / `low` |
| uncertainty_note | 条件必备 | 工时不确定或兜底估算时输出 |

### 6.6 cost_estimate 字段

| 字段 | 必要性 | 说明 |
|------|--------|------|
| parts_cost | 可选 | 零件费用预估 |
| labor_cost | 可选 | 工时费用预估 |
| total_cost | 可选 | 总费用预估 |
| currency | 可选 | 价格币种 |
| source | 条件必备 | `price_database` / `quotation_system` / `case_work_order` / `llm_generated` |
| source_confidence | 必备 | `high` / `medium` / `low` |
| uncertainty_note | 条件必备 | 价格不确定或兜底估算时输出 |

### 6.7 输出示例

```json
{
  "repair_plan": {
    "repair_target": {
      "target_name": "前氧传感器信号异常",
      "target_status": "confirmed",
      "cause_id": "CAUSE_O2_SENSOR_SIGNAL_ABNORMAL"
    },
    "target_type": "single_dtc",
    "repair_solution": {
      "repair_solution_id": "RS_O2_SENSOR_REPLACE",
      "repair_solution_name": "更换前氧传感器",
      "repair_solution_description": "当前维修目标为前氧传感器信号异常，建议更换前氧传感器。",
      "matched_cause_name": "前氧传感器信号异常",
      "matched_dtcs": ["P0130"],
      "solution_source": "structured_repair_knowledge",
      "source_confidence": "high"
    },
    "repair_method": "确认前氧传感器安装位置后，断开传感器连接器，拆下旧传感器，安装符合车型规格的新传感器，并重新连接线束。完成后清除故障码，并复查氧传感器数据流是否恢复正常。",
    "parts": [
      {
        "part_name": "前氧传感器",
        "quantity": 1,
        "part_type": "oem"
      }
    ],
    "labor_estimate": {
      "estimated_time": "0.5 - 1.0 小时",
      "source": "standard_repair_data",
      "source_confidence": "medium"
    },
    "cost_estimate": {
      "parts_cost": "参考零件价格",
      "labor_cost": "参考工时费用",
      "total_cost": "以门店最终报价为准",
      "source": "price_database",
      "source_confidence": "medium",
      "uncertainty_note": "价格会因地区、车型配置、零件类型和零件品牌不同而变化。"
    },
    "risk_level": "medium",
    "warning_note": "更换传感器前应确认零件规格与车型匹配，避免因型号不匹配导致故障复现。",
    "post_repair_validation": "维修完成后，建议清除故障码并重新扫描车辆；启动车辆后读取氧传感器相关数据流，确认信号变化正常；必要时进行路试，确认故障码不再复现。如维修后故障仍存在，应回到 Diagnostic Planning 继续检查线路、供电、接地或 ECU 相关问题。"
  }
}
```

当 `include_labor_price = false` 且用户没有询问价格时，可不输出 `labor_estimate` 和 `cost_estimate`。

大模型兜底工时示例：

```json
{
  "labor_estimate": {
    "estimated_time": "约 0.5 - 1.5 小时",
    "source": "llm_generated",
    "source_confidence": "low",
    "uncertainty_note": "该工时为基于通用维修经验的参考估算，实际工时需以车型、维修条件和门店检测结果为准。"
  }
}
```

### 6.8 信息不足输出示例

```json
{
  "repair_plan": null,
  "uncertainty_note": "当前缺少明确的维修目标，无法生成维修方案。",
  "missing_required_info": [
    "repair_target"
  ]
}
```

## 7. 边界规则

该 Skill **负责**：
- 基于明确的 repair_target 查询维修方案
- 输出维修方案（修什么）、维修方法（具体怎么修）
- 输出相关零部件、工具、风险提示
- 根据需要输出工时和价格
- 输出维修后验证建议
- 在结构化维修知识缺失时，输出低置信度兜底维修结果

该 Skill **不负责**：
- 诊断阶段的分析、判断和确认
- 直接执行维修动作

核心边界：Repair Planning **只在维修目标明确后回答“怎么修”，不负责判断“是不是这个原因”。**

## 8. 异常与兜底

兜底重点：**缺少明确维修目标时不生成维修方案；结构化维修知识缺失时可以低置信度兜底，但必须明确标记来源、置信度和不确定性。**

重点规则：
- 缺少 repair_target 时，不生成维修方案
- 只有候选原因排序、但原因未确认且用户未指定维修对象时，不自动进入 Repair Planning
- 用户明确指定某候选原因或零件怎么修时，可生成条件性维修方案
- 结构化维修知识未命中时，可调用大模型生成低置信度维修方案、维修方法、工时和价格
- 大模型兜底必须标记 `llm_generated` 和 `low` 置信度
- 大模型不得编造维修方案 ID 或零件编号
- 工时和价格可以低置信度兜底估算，但不得表达为标准工时、标准报价或最终报价
- 高风险维修不得仅基于大模型兜底输出详细操作指导
- symptom_case 且 `dtc_result = unknown` 时，若维修目标并不明确，应优先回到诊断链路补充 DTC 结果
- 维修后验证失败时，应回到 Diagnostic Planning 或 Cause Ranking

## 9. 验收标准

- 系统只在存在明确 repair_target 时触发 Repair Planning
- 能区分已确认原因、用户指定假设和用户指定维修对象；用户假设时输出条件性维修方案
- 能兼容 dtc_group、single_dtc、symptom_case、user_specified_target，但都必须基于明确 repair_target 输出
- 优先从结构化维修知识中获取维修方案；结构化数据缺失时可低置信度兜底，但必须标记来源和置信度
- 工时和价格优先来自可靠数据；缺少结构化数据时可低置信度兜底估算，但不得伪装成标准报价
- 输出应包含 `post_repair_validation`，用于支撑维修后闭环
- 大模型兜底结果必须低置信度标记，不得编造结构化 ID
- 顶层只输出 `repair_plan`、`uncertainty_note`、`missing_required_info`
