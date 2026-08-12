# RAG 0.8.0 Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Tool 中台五个强类型 RAG Tool 从 0.7.0 契约升级到当前运行中的 0.8.0，保持 Agent 请求、echo 和中台外层响应兼容。

**Architecture:** 继续使用本地 `myskills/*/tool-schema.json` 作为中台运行时契约，但从 RAG 0.8.0 的工具详情接口同步权威 input/output Schema，并重新附加中台 `x-extract`。不修改 handler 路径和注册中心调用链，只更新契约、验证脚本、测试和联调文档。

**Tech Stack:** Python 3.13、FastAPI、JSON Schema、httpx、pytest、uv。

## Global Constraints

- RAG 权威地址为 `http://172.16.67.169:8000`，期望 OpenAPI 版本必须等于 `0.8.0`。
- 五个 Tool 的 URL、名称和公共输入 `brand/model/year/dtc_codes/language` 不变。
- 中台外层响应继续使用 `code/message/data/trace_id/echo`。
- 缺少 `brand/model/dtc_codes` 时继续由中台返回 `40000`，不改变现有 Agent 错误语义。
- 保留五份本地契约中的 `additionalProperties=false` 和 `x-extract`。
- 不覆盖当前工作区未提交的日志模块修改，不暂存日志相关文件。
- 不修改 Repair Agent、编排层代码、RAG handler 路径或超时配置。

---

### Task 1: 用失败测试锁定 0.8.0 输出契约

**Files:**
- Modify: `tests/test_five_tool_contracts.py`

**Interfaces:**
- Consumes: 五份 `myskills/*/tool-schema.json`。
- Produces: 对 `status/message`、无 `null` Schema 和组对象可选性的回归约束。

- [ ] **Step 1: 增加 0.8.0 Schema 断言**

在参数化的五工具契约测试中增加：

```python
output_schema = contract["output_schema"]
properties = output_schema["properties"]
assert properties["status"]["enum"] == ["ok", "no_data", "partial", "missing_input"]
assert properties["message"]["type"] == "string"
assert "status" in output_schema["required"]
assert "message" in output_schema["required"]
assert "null" not in json.dumps(output_schema, ensure_ascii=False)
```

对 Cause、Diagnostic、Repair 额外断言 `group` 不在顶层 `required` 中。

- [ ] **Step 2: 运行测试确认因本地 0.7.0 Schema 失败**

Run:

```powershell
uv run --extra dev pytest tests/test_five_tool_contracts.py -v
```

Expected: FAIL，原因是缺少 `status` 或输出 Schema 仍包含 `null`。

---

### Task 2: 同步五份 RAG 0.8.0 契约

**Files:**
- Modify: `sync_rag_five_tool_contracts.py`
- Modify: `myskills/dtc-context-skill/tool-schema.json`
- Modify: `myskills/dtc-grouping-skill/tool-schema.json`
- Modify: `myskills/cause-ranking-skill/tool-schema.json`
- Modify: `myskills/diagnostic-planning-skill/tool-schema.json`
- Modify: `myskills/repair-planning-skill/tool-schema.json`

**Interfaces:**
- Consumes: `GET /openapi.json` 和 `GET /api/v1/tools/{tool_name}`。
- Produces: 五份带中台 `x-extract` 的 0.8.0 本地契约。

- [ ] **Step 1: 修改同步脚本版本门禁**

把脚本中的：

```python
if openapi.get("info", {}).get("version") != "0.7.0":
```

改为：

```python
expected_version = "0.8.0"
actual_version = openapi.get("info", {}).get("version")
if actual_version != expected_version:
    raise RuntimeError(f"expected RAG {expected_version}, got {actual_version}")
```

同步流程继续执行：远端 input Schema 设置 `additionalProperties=False`，重新附加现有
`EXTRACT_MAPPING`，远端 output Schema原样作为本地输出契约。

- [ ] **Step 2: 从权威实例同步五份契约**

Run:

```powershell
uv run python sync_rag_five_tool_contracts.py --base-url http://172.16.67.169:8000
```

Expected: 五份 `tool-schema.json` 更新成功，远端版本显示 `0.8.0`。

- [ ] **Step 3: 检查同步差异**

Run:

```powershell
git diff --stat -- myskills sync_rag_five_tool_contracts.py
git diff --check -- myskills sync_rag_five_tool_contracts.py
```

Expected: 只有五份契约和同步脚本发生预期变化，无格式错误；每份 input Schema 仍包含
`x-extract`，output Schema 包含 `status/message` 且不存在 `null` 类型。

- [ ] **Step 4: 运行 Task 1 测试确认通过**

Run:

```powershell
uv run --extra dev pytest tests/test_five_tool_contracts.py -v
```

Expected: PASS。

---

### Task 3: 升级运行时契约验证脚本

**Files:**
- Modify: `verify_rag_runtime_contracts.py`
- Modify: `verify_rag_chain.py`

**Interfaces:**
- Consumes: 五份 0.8.0 本地契约、RAG 强类型接口和中台 `/invoke`。
- Produces: 可重复执行的 0.8.0 真实链路验证。

- [ ] **Step 1: 增加通用无 null 断言函数**

在 `verify_rag_runtime_contracts.py` 增加：

```python
def assert_no_json_null(value: object, path: str = "$" ) -> None:
    if value is None:
        raise RuntimeError(f"JSON null found at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_json_null(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_json_null(item, f"{path}[{index}]")
```

- [ ] **Step 2: 验证 0.8.0 业务状态**

每次强类型调用在 JSON Schema 校验后执行：

```python
assert_no_json_null(body)
if body.get("status") not in {"ok", "partial", "no_data", "missing_input"}:
    raise RuntimeError(f"invalid business status: {body.get('status')}")
if not isinstance(body.get("message"), str):
    raise RuntimeError("business message must be a string")
```

脚本文档字符串和输出文本中的版本改为 `0.8.0`。

- [ ] **Step 3: 中台链路检查 `data.status/data.message`**

在 `verify_rag_chain.py::invoke()` 解包成功信封后增加：

```python
data = body["data"]
if data.get("status") not in {"ok", "partial", "no_data", "missing_input"}:
    raise RuntimeError(f"invalid business status: {data.get('status')}")
if not isinstance(data.get("message"), str):
    raise RuntimeError("business message must be a string")
return data
```

- [ ] **Step 4: 直接验证 RAG 运行时**

Run:

```powershell
uv run python verify_rag_runtime_contracts.py --base-url http://172.16.67.169:8000 --timeout 60
```

Expected: 五份远端 Schema 与本地契约一致，五个强类型响应全部通过 JSON Schema 和无 null 检查。

---

### Task 4: 更新编排层示例与文档

**Files:**
- Modify: `examples/orchestrator/README.md`
- Modify: `README.md`
- Modify: `docs/PROJECT_CODE_READING_GUIDE.md`
- Modify: `tests/test_orchestrator_examples.py`

**Interfaces:**
- Consumes: 五份 0.8.0 Schema 和当前编排请求示例。
- Produces: 可直接发给编排层的 0.8.0 请求/响应说明。

- [ ] **Step 1: 更新版本说明**

把五工具相关的 `0.7.0` 文案改为 `0.8.0`，并明确：

```text
中台外层 code=0 只表示 Tool 调用完成；业务结果读取 data.status，业务提示读取 data.message。
```

- [ ] **Step 2: 更新五个响应 JSON**

每个 `data` 增加符合真实返回的：

```json
"status": "partial",
"message": "已返回部分检索结果，请结合 meta 和 issues 复核。"
```

把旧示例中的 `null` 按 0.8.0 规则改为 `""`、`[]` 或省略该字段。请求 JSON 不修改。

- [ ] **Step 3: 强化文档 JSON Schema 测试**

在 `tests/test_orchestrator_examples.py` 对每个文档响应增加：

```python
assert response["data"]["status"] in {"ok", "partial", "no_data", "missing_input"}
assert isinstance(response["data"]["message"], str)
assert_no_null(response["data"])
```

其中 `assert_no_null` 在测试文件内递归检查字典和数组。

- [ ] **Step 4: 运行示例测试**

Run:

```powershell
uv run --extra dev pytest tests/test_orchestrator_examples.py -v
```

Expected: PASS，所有请求满足 input Schema，所有示例 `data` 满足 output Schema 且无 JSON null。

---

### Task 5: 完整回归与隔离提交

**Files:**
- Include only: 本计划列出的契约、脚本、文档和相关测试文件。
- Exclude: `.env.example`、`app/core/logging_config.py`、`app/core/log_context.py`、`app/main.py`、
  `app/api/v1/endpoints/tools.py`、`app/core/registry.py`、`app/services/rag_client.py`、
  `tests/test_logging_phase1_temp.py` 及其他未提交日志改动。

**Interfaces:**
- Consumes: Tasks 1–4 的全部结果。
- Produces: 可独立回滚的 RAG 0.8.0 适配提交。

- [ ] **Step 1: 运行相关测试**

Run:

```powershell
uv run --extra dev pytest tests/test_five_tool_contracts.py tests/test_orchestrator_examples.py tests/test_registry_slot_extraction.py tests/test_rag_client.py -v
```

Expected: 全部通过。

- [ ] **Step 2: 运行完整测试**

Run:

```powershell
uv run --extra dev pytest
```

Expected: 当前全部测试通过；日志临时测试若仍在工作区，也必须通过，但不纳入本次提交。

- [ ] **Step 3: 核对改动范围**

Run:

```powershell
git status --short
git diff --check
```

Expected: RAG 0.8.0 文件与日志改动可明确区分；不覆盖或暂存日志模块修改。

- [ ] **Step 4: 创建独立提交**

只暂存本计划文件，提交信息：

```text
feat: align five tool contracts with rag 0.8.0
```

提交后再次运行 `git show --name-only --stat HEAD`，确认没有日志模块文件混入。
