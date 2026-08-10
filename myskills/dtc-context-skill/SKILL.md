---
name: dtc-context
description: 将单个 DTC 解析为下游诊断工作流可复用的标准化背景上下文。该 Skill 负责解析 DTC 的含义、所属系统、触发条件、相关零件和相关数据流，并在信息不足时保留不确定性。
tools:
  - global_tool: dtc_context_service
    description: 基于结构化 DTC 数据、品牌专属资料以及可选的大模型兜底，解析 DTC 背景上下文。
    required: true
---

# DTC Context Skill

## 1. 目标

该 Skill 将单个 DTC 转换为可复用的背景对象，供后续诊断 Agent 使用。

它主要回答：
- 当前 DTC 表示什么？
- 它属于哪个系统？
- 通常在什么条件下触发？
- 通常关联哪些相关零件和数据流？

其重点是背景解析，而不是诊断推理或维修决策。

## 2. 触发条件

在以下场景中使用该 Skill：
- 用户明确询问某个 DTC 的含义或背景信息。
- 下游工作流在进行 DTC 分组、原因排序或诊断规划前，需要先获取 DTC 背景。
- 新的诊断报告中包含需要理解的 DTC。
- 当前任务切换到另一个 DTC，或清码后重新扫出新的 DTC。

典型用户问题包括：
- “P0171 是什么意思？”
- “宝马 P0300 是什么故障？”
- “这个故障码属于哪个系统？”
- “这个 DTC 一般在什么条件下产生？”
- “这个故障码和氧传感器有关吗？”
- “这个故障码涉及哪些数据流？”

## 3. 输入信息

### 核心输入
- dtc_code：必填
- brand：当需要品牌语义解析时必填

### 辅助输入
- vehicle_info：可选
  - model
  - year
  - system
  - VIN
  - known configuration

车辆信息可提高解析精度和消歧能力，但不是核心输入。如果辅助信息与查询结果冲突，应标记不确定性，而不是直接覆盖解析结果。

## 4. 解析规则

### 4.1 判断解析类型

选择以下之一：
- generic_obd：通用 OBD-II 解析
- brand_specific：品牌/车型专属解析
- uncertain：由于信息不足、冲突或缺少可靠资料，无法稳定解释

### 4.2 优先级顺序

1. 当有品牌信息时，优先采用品牌语义解析。
2. 如果品牌资料与通用 OBD-II 解释存在差异，优先采用品牌资料。
3. 如果结果存在歧义、不完整或冲突，应输出不确定性，而不是给出过度确定的解释。

### 4.3 信息不足处理

- 如果缺少 dtc_code，不触发该 Skill。
- 如果 DTC 编码不完整或疑似输入错误，应提示用户检查编码。
- 通用 OBD-II 标准码在缺少品牌时可进行降级解析，并标记为 generic_obd。
- 需要品牌语义解析的 DTC 若缺少品牌信息，应提示补充品牌、VIN 或车型信息，并标记为 uncertain。
- 如果无法判断当前 DTC 应采用通用解析还是品牌解析，也应标记为 uncertain。

## 5. Tool 使用

优先通过全局工具服务解析 DTC。

### Tool 契约
- Tool 名称：dtc_context_service
- 作用：查询结构化 DTC 资料、品牌 DTC 数据库，以及可选的大模型兜底。
- 输入：dtc_code、brand、vehicle_info
- 输出：标准化的 DTC Context 对象

### 兜底策略
如果工具或知识源没有返回稳定结果：
- 调用大模型兜底路径
- 将 source_type 设置为 llm_generated
- 将 confidence 设置为 low
- 输出 uncertainty_note
- 不要将结果伪装为官方或已验证的资料

## 6. 输出结构

该 Skill 必须返回如下标准化对象：

```json
{
  "dtc_context": {
    "dtc_code": "P0171",
    "brand": "generic",
    "dtc_description": "System too lean (Bank 1)",
    "system": "Engine system",
    "subsystem": "Fuel trim / air-fuel ratio control",
    "trigger_condition": "The ECU detects that Bank 1 is running too lean and exceeds the calibration threshold.",
    "related_parts": [
      "MAF sensor",
      "O2 sensor",
      "Vacuum hoses",
      "Intake path",
      "Fuel pump / pressure regulator related parts"
    ],
    "related_datastreams": [
      "Short-term fuel trim",
      "Long-term fuel trim",
      "MAF value",
      "O2 sensor voltage"
    ],
    "interpretation_type": "generic_obd",
    "source_type": "generic_obd_database",
    "confidence": "medium",
    "uncertainty_note": "Current result is based on generic OBD-II knowledge and not brand-specific data."
  }
}
```

### 必填输出字段
- dtc_code
- interpretation_type
- source_type
- confidence

### 在可稳定解析时，建议输出的字段
- dtc_description
- system
- subsystem
- trigger_condition
- related_parts
- related_datastreams
- uncertainty_note

## 7. 字段语义

- dtc_description：对 DTC 含义的通俗解释
- system：故障码所属的主要系统
- subsystem：更细的子系统或功能域
- trigger_condition：DTC 通常在什么条件下被记录
- related_parts：与该 DTC 背景相关的零件、模块、传感器、执行器、线路或连接器等
- related_datastreams：与该 DTC 相关的数据流或信号通道
- interpretation_type：generic_obd、brand_specific 或 uncertain
- source_type：generic_obd_database、brand_dtc_data、dtc_database 或 llm_generated
- confidence：high、medium 或 low
- uncertainty_note：当信息不完整、存在冲突或置信度较低时必须输出
- missing_required_info：当结果因为缺少必要信息而不确定时必须输出

## 8. 不确定性与兜底规则

当该 Skill 无法给出稳定解释时：
- 不要编造确定性解释
- 输出 uncertainty_note
- 在需要时补充 missing_required_info
- 将 confidence 标记为 low
- 如果采用大模型兜底，应明确标记 source_type 为 llm_generated

### 信息不足示例

```json
{
  "dtc_context": {
    "dtc_code": "A1234",
    "interpretation_type": "uncertain",
    "confidence": "low",
    "uncertainty_note": "The DTC requires brand-specific interpretation, but no reliable brand or vehicle information was provided.",
    "missing_required_info": [
      "brand"
    ]
  }
}
```

### 大模型兜底示例

```json
{
  "dtc_context": {
    "dtc_code": "B7890",
    "brand": "unknown",
    "dtc_description": "No stable DTC reference was found; this appears to be related to a body or electrical subsystem based on the code pattern.",
    "system": "Body / electrical system",
    "related_parts": [
      "Body control module",
      "Related wiring",
      "Related sensor or actuator"
    ],
    "interpretation_type": "uncertain",
    "source_type": "llm_generated",
    "confidence": "low",
    "uncertainty_note": "This is a low-confidence background reference only and should not be treated as an official brand explanation."
  }
}
```

## 9. 边界规则

该 Skill 不能：
- 进行诊断推理
- 对原因进行排序
- 生成维修建议
- 确认根因
- 生成检查计划
- 将相关零件或相关数据流当作最终根因

相关零件和相关数据流仅表示背景信息，不代表候选原因或维修意见。

## 10. 验收标准

当该 Skill 满足以下条件时可认为完成：
- 能正确触发用户对单个 DTC 的询问，或下游链路对 DTC 背景信息的需求
- 能返回主要的 DTC 背景字段
- 能区分 generic_obd、brand_specific 和 uncertain
- 能正确标记 source type
- 当信息不足时能保留不确定性
- 不会将低置信度输出伪装为官方或已验证资料
