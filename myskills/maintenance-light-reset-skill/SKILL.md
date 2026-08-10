---
name: maintenance-light-reset
description: 基于车辆品牌、车型、年款匹配保养归零操作资料或实测案例，支持资料指引（guide）和授权执行（execute）两种方式完成保养灯归零。该 Skill 负责 SOP 输出或设备执行，不判断是否需要保养、不处理故障诊断、不绕过用户确认。
tools:
  - global_tool: maintenance_light_reset_service
    description: 匹配保养归零资料、官方资料或实测案例，输出 SOP 指引；或在设备支持且用户确认后执行保养灯归零。
    required: true
---

# Maintenance Light Reset Skill

## 1. 目标

该 Skill 是操作能力库中的 SOP / 执行型能力，负责基于车辆品牌、车型、年款，匹配保养归零操作资料、官方资料或实测案例，并支持资料指引和授权执行两种方式完成保养灯归零任务。

```
action_mode = guide
  资料指引模式：匹配资料 → 按资料输出 SOP → 用户自行操作

action_mode = execute
  授权执行模式：检查设备能力 → 提示用户确认 → 调用设备执行保养归零 → 返回执行结果
```

它主要回答：
- 怎么做保养灯归零？
- 是按资料指引操作，还是在设备支持且用户确认后直接执行？

核心链路：

```
品牌 + 车型 + 年款
+ VIN / 设备型号 / 软件版本 / 设备连接状态
  ↓
判断 action_mode
  ↓
guide：匹配资料并输出步骤化 SOP
execute：确认设备能力与用户授权后执行保养归零
  ↓
输出 SOP 指引或执行结果
```

## 2. 触发条件

当用户明确询问保养归零、保养灯归零、保养到期复位等操作时，使用本 Skill。

典型问题包括：
- “奔驰 C200 2010 款保养灯怎么归零？”
- “保养到期怎么复位？”
- “换完机油后保养灯怎么消掉？”
- “保养归零入口在哪里？”
- “用 X-431 PAD V 怎么做保养灯归零？”
- “仪表提示 Service Due 怎么清除？”
- “帮我直接执行保养归零。”
- “能不能自动把保养灯归零？”

默认规则：
- 用户问“怎么做”“入口在哪里”“步骤是什么”，默认进入 **guide** 模式
- 用户问“帮我执行”“直接归零”“自动复位”，可进入 **execute** 模式
- 用户只说“灯亮了怎么消除”，且无法判断是否为保养提示时，应先澄清
- 若判断为故障灯、胎压灯、刹车片提示灯、安全气囊灯等非保养提示，**不进入该 Skill**

## 3. 输入信息

### 核心输入

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| brand | 车辆品牌 | 必备 | 用于匹配品牌资料或执行能力 |
| model | 车型 | 必备 | 用于匹配具体车型步骤或设备能力 |
| year | 年款 | 必备 | 用于匹配适用年款和操作资料 |
| action_mode | 操作模式 | 可选 | `guide` / `execute`；默认 `guide` |

### 增强输入

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| vin | VIN | 可选增强 | 用于辅助确认车型、年款和配置 |
| device_model | 元征设备型号 | 可选增强 | 用于辅助判断界面、功能入口或执行能力差异 |
| software_version | 软件版本 | 可选增强 | 用于辅助判断功能入口和资料适配性 |

### execute 模式条件输入

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| device_connection_status | 设备连接状态 | 条件必备 | `action_mode = execute` 时需要确认设备连接状态 |
| device_capability | 设备能力 | 条件必备 | `action_mode = execute` 时用于判断当前设备是否支持执行 |
| user_confirmation | 用户确认 | 条件必备 | `action_mode = execute` 时，执行前必须获得用户确认 |

说明：
- 品牌、车型、年款缺失时，应优先补充关键信息
- VIN、设备型号、软件版本缺失，不阻断 guide 模式输出
- execute 模式下，设备连接状态、设备能力和用户确认是必要条件
- 用户提到的仪表提示、已进入某个界面、操作失败等信息，可作为当前上下文使用，不作为固定输入字段

## 4. 处理规则

### 4.1 判断 action_mode

系统应先判断本次任务是资料指引还是授权执行。

```
action_mode = guide  →  输出 SOP 指引，用户自行操作
action_mode = execute  →  用户确认后，调用设备执行保养归零
```

默认规则：
- 用户询问操作方法时，进入 `guide`
- 用户明确要求自动执行时，进入 `execute`
- execute 模式缺少设备能力、连接状态或用户确认时，**不得执行**

### 4.2 匹配保养归零资料或实测案例

系统应基于品牌、车型、年款匹配保养归零操作资料、官方资料或实测案例。

匹配优先级：

```
品牌 + 车型 + 年款
  ↓
品牌 + 车型 + 相近年款
  ↓
品牌 + 同平台 / 同系统
  ↓
通用保养归零路径
```

如果匹配到精确案例，应优先输出精确案例。  
如果未匹配到精确案例，可输出通用路径，但必须明确提示：

> 未匹配到该车型年款的精确案例，以下为通用保养归零路径，具体操作以实际设备界面为准。

**不得**把其他车型、其他年款、其他设备的案例包装成当前车型的精确步骤。

### 4.3 guide 模式：按资料输出 SOP 步骤

当 `action_mode = guide` 时，应按照资料中的步骤、图片、视频或案例截图组织输出。

`steps` 应承载资料中的主要操作内容，包括：
- 操作入口
- 操作动作
- 界面提示
- 图文 / 视频引用
- 资料中的注意事项
- 资料中的结果提示

**不额外扩展**资料中没有的操作路径、操作步骤或判断结论。

步骤字段示例：

```json
{
  "step_no": 1,
  "instruction": "选择【IC】进入仪表系统。",
  "source_ref": "图1"
}
```

### 4.4 execute 模式：用户确认后执行保养归零

当 `action_mode = execute` 时，系统必须先确认：
- 品牌、车型、年款已明确
- 当前设备支持该车型保养归零
- 当前设备连接状态满足执行要求
- 用户已明确确认执行

执行前应向用户说明即将执行的操作。示例提示：

> 即将对当前车辆执行保养灯归零。执行后，仪表保养周期可能被重置。请确认车辆已完成实际保养，是否继续？

用户确认后，才可调用设备执行保养归零。  
执行完成后，应返回设备执行结果。

执行失败时，不直接推断为车辆故障，只说明设备返回结果，并提示可能与车型选择、设备连接、软件版本、功能支持或操作条件有关。

核心原则：**execute 模式不是无条件自动执行，而是在设备支持、条件满足、用户确认后执行。**

### 4.5 标记资料来源与置信度

guide 模式应标记资料来源类型和置信度，用于说明当前 SOP 的可靠程度。

| source_type | 中文含义 | 适用情况 | source_confidence |
|-------------|----------|----------|-------------------|
| exact_case | 精确实测案例 | 同品牌、同车型、同年款，且有实测步骤、图片或视频 | high |
| similar_case | 相近案例 | 同品牌、同车型，但年款相近或配置存在差异 | medium |
| official_manual | 官方资料 | 来自官方资料、产品资料或标准操作说明 | high / medium |
| general_path | 通用路径 | 未命中精确资料，仅能给出通用保养归零方向 | low |
| llm_generated | 大模型兜底 | 无资料命中时，仅输出通用操作方向，不生成具体操作路径 | low |

说明：
- `source_confidence` 表示当前 SOP 的资料可信程度
- 精确案例优先，其次是相近案例或官方资料
- 通用路径和大模型兜底只能作为低置信度参考
- 低置信度输出必须附带 `uncertainty_note`

### 4.6 不扩展资料，不绕过用户确认

在 guide 模式下，应基于已匹配资料、官方资料或实测案例输出 SOP，不额外生成资料中没有的具体操作步骤、判断结论或车型适配结论。

在 execute 模式下，必须在设备能力支持、连接状态满足要求，并获得用户明确确认后，才可调用设备执行保养归零。

核心原则：**资料不确定时，不伪装成精确资料；用户未确认时，不执行设备操作。**

## 5. Tool 使用

优先通过全局工具服务完成资料匹配或设备执行。

### Tool 契约
- Tool 名称：`maintenance_light_reset_service`
- 作用：匹配保养归零资料并输出 SOP；或在设备支持且用户确认后执行保养灯归零
- 输入：`brand`、`model`、`year`、`action_mode`，及可选 / 条件字段
- 输出：标准化的 `maintenance_reset_result` 对象

### 兜底策略

| 场景 | 处理方式 |
|------|----------|
| 缺少品牌、车型、年款 | 先补充关键信息，输出 `missing_required_info` |
| 非保养提示 | 不进入该 Skill |
| 未命中精确资料 | 输出通用路径，标记 `general_path` 或 `llm_generated`，`source_confidence = low` |
| 设备不支持自动执行 | 可降级为 guide 模式，或返回 `execution_status = not_supported` |
| 用户未确认 | 返回 `execution_status = awaiting_confirmation`，不执行设备操作 |
| 执行失败 | 返回设备结果，不推断为车辆故障 |

## 6. 输出结构

核心输出为 `maintenance_reset_result`：
- guide 模式输出 `maintenance_reset_guide`
- execute 模式输出 `execution_result`
- 两种模式共享 `action_mode`、`uncertainty_note` 和 `missing_required_info`

### 6.1 顶层输出字段

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| action_mode | 操作模式 | 必备 | `guide` / `execute` |
| maintenance_reset_guide | 保养归零指引 | 条件必备 | guide 模式输出 |
| execution_result | 执行结果 | 条件必备 | execute 模式输出 |
| uncertainty_note | 不确定性说明 | 条件必备 | 资料不确定、设备不支持、执行失败等情况输出 |
| missing_required_info | 缺失必要信息 | 条件必备 | 缺少品牌、车型、年款或执行必要条件时输出 |

### 6.2 maintenance_reset_guide 字段

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| applicable_vehicle | 适用车型 | 必备 | 品牌、车型、年款 |
| source_type | 资料来源类型 | 必备 | `exact_case` / `similar_case` / `official_manual` / `general_path` / `llm_generated` |
| source_confidence | 来源置信度 | 必备 | `high` / `medium` / `low` |
| steps | SOP 步骤 | 必备 | 按资料输出操作入口、操作步骤、图文说明、结果提示和注意事项 |
| uncertainty_note | 不确定性说明 | 条件必备 | 未命中精确案例、设备版本差异、图片缺失等说明 |

### 6.3 steps 字段

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| step_no | 步骤编号 | 必备 | 当前步骤序号 |
| instruction | 操作说明 | 必备 | 按资料输出操作入口、操作动作、界面提示、注意事项或结果提示 |
| source_ref | 来源引用 | 可选 | 图示、视频片段、资料段落或案例截图 |

### 6.4 execution_result 字段

| 字段 | 中文含义 | 必要性 | 说明 |
|------|----------|--------|------|
| execution_status | 执行状态 | 必备 | `awaiting_confirmation` / `success` / `failed` / `cancelled` / `not_supported` |
| executed_action | 执行动作 | 条件必备 | 例如“保养灯归零” |
| device_message | 设备返回信息 | 可选 | 设备返回的执行提示、错误信息或状态说明 |
| confirmation_prompt | 确认提示 | 条件必备 | 等待用户确认时输出 |
| uncertainty_note | 不确定性说明 | 条件必备 | 设备不支持、执行失败或状态不明确时输出 |

说明：
- `awaiting_confirmation`：已准备执行，但尚未获得用户确认
- `success`：设备返回执行成功
- `failed`：设备执行失败
- `cancelled`：用户取消
- `not_supported`：当前设备或车型不支持自动执行

### 6.5 guide 模式输出示例

```json
{
  "action_mode": "guide",
  "maintenance_reset_guide": {
    "applicable_vehicle": {
      "brand": "Mercedes-Benz",
      "model": "C200",
      "year": "2010"
    },
    "source_type": "exact_case",
    "source_confidence": "high",
    "steps": [
      {
        "step_no": 1,
        "instruction": "选择【IC】进入仪表系统。",
        "source_ref": "图1"
      },
      {
        "step_no": 2,
        "instruction": "选择【保养归零】。",
        "source_ref": "图2"
      },
      {
        "step_no": 3,
        "instruction": "根据设备界面提示选择需要复位的保养项目，并按提示执行。",
        "source_ref": "图3"
      },
      {
        "step_no": 4,
        "instruction": "资料显示，执行完成后设备会提示成功，仪表保养提示应消失或显示新的保养周期。",
        "source_ref": "图4"
      }
    ]
  }
}
```

### 6.6 execute 模式确认示例

```json
{
  "action_mode": "execute",
  "execution_result": {
    "execution_status": "awaiting_confirmation",
    "executed_action": "保养灯归零",
    "confirmation_prompt": "即将对当前车辆执行保养灯归零。执行后，仪表保养周期可能被重置。请确认车辆已完成实际保养，是否继续？"
  }
}
```

### 6.7 execute 模式执行结果示例

```json
{
  "action_mode": "execute",
  "execution_result": {
    "execution_status": "success",
    "executed_action": "保养灯归零",
    "device_message": "设备返回：保养归零执行成功。"
  }
}
```

### 6.8 信息不足输出示例

```json
{
  "action_mode": "guide",
  "missing_required_info": [
    "品牌",
    "车型",
    "年款"
  ],
  "uncertainty_note": "缺少品牌、车型或年款信息，暂无法匹配保养归零资料。"
}
```

## 7. 边界规则

该 Skill **负责**：
- 基于品牌、车型、年款匹配保养归零资料或实测案例
- 在 guide 模式下，按资料输出步骤化 SOP
- 在 execute 模式下，检查设备能力、连接状态和执行条件
- 执行前提示用户将要执行的操作，并等待用户确认
- 用户确认后，调用设备执行保养灯归零
- 输出资料来源、置信度、不确定性说明或设备执行结果

该 Skill **不负责**：
- 判断车辆是否需要保养，或保养是否已完成
- 处理非保养提示或故障诊断
- 生成维修方案
- 在用户未确认时执行设备操作

核心边界：本 Skill 只负责保养归零的资料指引或授权执行，**不负责诊断、不负责维修，也不绕过用户确认**。

## 8. 异常与兜底

兜底重点：**资料不确定时，不伪装成精确资料；执行不确定时，不绕过用户确认。**

重点规则：
- 缺少品牌、车型、年款时，先补充关键信息
- 非保养提示不进入该 Skill
- 未命中精确资料时，只输出通用路径，并标记低置信度和不确定性
- 当前设备不支持自动执行时，可降级为 guide 模式
- 用户未确认时，不执行设备操作
- 保养归零失败时，不直接推断为车辆故障，仅返回设备结果并提示检查车型、设备、软件版本和连接状态

## 9. 验收标准

- 能区分 guide（输出 SOP 指引）与 execute（用户确认后调用设备执行）
- 能基于品牌、车型、年款匹配资料，并按资料输出步骤化 SOP
- execute 执行前必须确认设备支持、连接状态满足要求，并获得用户确认
- 能输出资料来源和置信度；无精确资料时，不编造操作路径，不伪装成精确车型步骤
- 低置信度输出附带 `uncertainty_note`；用户未确认时不执行设备操作
