# Tool 中台适配 RAG 0.8.0 设计方案

## 1. 目标

将 Tool 中台的五个 RAG Tool 契约从 0.7.0 升级到 0.8.0，避免 RAG 调用成功后被中台判定为
出参校验失败。

## 2. 修改范围

### 2.1 同步五份 Tool Schema

更新以下文件的 `input_schema` 和 `output_schema`：

```text
myskills/dtc-context-skill/tool-schema.json
myskills/dtc-grouping-skill/tool-schema.json
myskills/cause-ranking-skill/tool-schema.json
myskills/diagnostic-planning-skill/tool-schema.json
myskills/repair-planning-skill/tool-schema.json
```

Schema 来源以 RAG 运行时接口为准：

```text
GET http://172.16.67.169:8000/api/v1/tools/{tool_name}
```

同步后保留中台自己的 `x-extract` 槽位映射和未知字段过滤规则。

### 2.2 适配 0.8.0 返回结构

五个 Tool 的 `data` 都接受新增业务字段：

```json
{
  "status": "ok",
  "message": ""
}
```

`status` 支持：

```text
ok
partial
no_data
missing_input
```

同时使用 0.8.0 的无 `null` 契约：

- 空列表返回 `[]`；
- 空展示文本返回 `""`；
- 未知数字、ID、枚举和对象字段直接省略。

### 2.3 更新同步和验证脚本

修改：

```text
sync_rag_five_tool_contracts.py
verify_rag_runtime_contracts.py
verify_rag_chain.py
```

主要变化：

- 期望 RAG 版本由 `0.7.0` 改为 `0.8.0`；
- 检查五个响应包含 `status/message`；
- 检查响应中不存在 JSON `null`；
- 验证实际 RAG 响应符合本地 Schema。

### 2.4 更新测试和联调文档

更新五工具契约测试、编排层响应示例及版本说明：

```text
tests/test_five_tool_contracts.py
tests/test_orchestrator_examples.py
examples/orchestrator/README.md
README.md
docs/PROJECT_CODE_READING_GUIDE.md
```

请求示例基本不变，响应示例增加 `data.status/data.message`，并删除所有 `null` 示例。

## 3. 不修改的内容

以下内容保持不变：

- 五个 Tool 名称；
- 五个 RAG 接口 URL；
- 请求字段 `brand/model/year/dtc_codes/language`；
- Agent 顶层 ID 提取和 `echo`；
- 中台外层 `code/message/data/trace_id/echo` 响应；
- 槽位提取整体逻辑；
- 中台 15 秒普通工具、50 秒 Cause 超时；
- Repair Agent 和编排层代码。

中台成功响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "ok",
    "message": "",
    "contexts": [],
    "issues": [],
    "uncertainty_note": "",
    "missing_required_info": []
  },
  "trace_id": "trace-001",
  "echo": {
    "request_id": "req-001"
  }
}
```

## 4. 缺少必填参数的处理

中台继续保持当前严格校验：

```text
缺少 brand/model/dtc_codes → HTTP 400，code=40000
```

不改成 RAG 的 HTTP 200 `missing_input` 行为，避免改变 Agent 现有错误处理。

但本地输出 Schema仍接受 RAG 返回的 `status=missing_input`。

## 5. 实施步骤

```text
1. 保存当前工作区未提交的日志模块修改，不覆盖
2. 从 RAG 0.8.0 运行时读取五份权威 Schema
3. 同步五份本地 Tool Schema并保留 x-extract
4. 更新版本检查和验证脚本
5. 更新五工具契约测试
6. 更新联调响应示例和版本文档
7. 运行完整测试
8. 直连 RAG 验证五个强类型接口
9. 通过中台 /invoke 验证五个 Tool
10. 单独提交 RAG 0.8.0 适配改动
```

## 6. 验收标准

- 五个 Tool 实际调用 RAG 0.8.0 不返回 `50001`；
- 五个 `data` 均包含合法的 `status/message`；
- RAG 返回对象中不存在 JSON `null`；
- 中台响应仍包含 `code/message/data/trace_id/echo`；
- Agent 请求参数及 `echo` 行为不变；
- 五工具联调示例符合最新 Schema；
- 原有测试和新增 0.8.0 契约测试全部通过。

## 7. 不修改的风险

如果不升级：

```text
RAG 0.8.0 返回 status/message
    ↓
中台仍按 0.7.0 Schema 校验
    ↓
中台返回 code=50001
    ↓
Agent 认为 Tool 调用失败
```

因此该适配应在日志优化之前完成并单独验证。

## 8. 回滚方案

- 本次不修改数据库和外部接口路径；
- 如上线验证失败，可回滚本次独立 Git 提交；
- 回滚中台时必须同时确认 RAG 是否仍提供 0.7.0，不能让 0.7.0 中台继续调用纯 0.8.0 RAG；
- 发布期间禁止 RAG 0.7.0 和 0.8.0 混部。
