# Agent Request Echo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter every invoke request to declared Tool slots while echoing all top-level `id`/`*_id` scalar fields in every invoke success and error response.

**Architecture:** Extend the existing request ContextVar middleware with an independent `echo_ctx`, populated from the raw top-level JSON object before route validation and reset with a token after each request. Keep Agent IDs out of flat `arguments`, make invoke response construction read the request echo, and make tools without `x-extract` use `input_schema.properties` as their default projection.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, ContextVar, jsonschema, pytest, FastAPI TestClient.

## Global Constraints

- Echo only case-sensitive top-level fields named `id` or ending in `_id`.
- Echo values may be JSON strings or integers; `null` is omitted; booleans, arrays, and objects produce invoke `code=40000`.
- Never recursively echo IDs from `arguments` or nested data.
- Every `POST /api/v1/tools/{tool_name}/invoke` response includes `echo`; missing IDs produce `{}`.
- Do not change the five RAG 0.7.0 input/output schemas or the RAG service.
- Preserve `code`, `message`, `data`, and envelope `trace_id` semantics.
- Do not add `.workbuddy/` to Git.

## Test Command Convention

Define this PowerShell helper once, then use it for every pytest step:

```powershell
function Invoke-RoxiePytest {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PytestArgs)
    $env:ROXIE_PYTEST_ARGS = ConvertTo-Json -Compress -InputObject $PytestArgs
    & 'C:\Users\shifeng.wang\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\python.exe' -c "import json,os,site; site.addsitedir(r'C:\Users\shifeng.wang\AppData\Local\Temp\roxie-platform-testdeps'); site.addsitedir(r'D:\roxie_management_platform\.venv_new\Lib\site-packages'); import pytest; raise SystemExit(pytest.main(json.loads(os.environ['ROXIE_PYTEST_ARGS'])))"
}
```

---

### Task 1: Dynamic echo ID extraction and flat request separation

**Files:**
- Modify: `app/core/responses.py`
- Modify: `app/api/v1/schemas.py`
- Create: `tests/test_invoke_echo_request.py`

**Interfaces:**
- Produces: `echo_ctx: ContextVar[dict[str, str | int]]`
- Produces: `is_echo_id_key(field_name: str) -> bool`
- Produces: `extract_echo_ids(payload: object) -> dict[str, str | int]`
- Consumes: `ToolInvokeRequest.merge_flat_payload(data)` for flat request compatibility.

- [ ] **Step 1: Write failing tests for exact ID matching and flat request separation**

```python
def test_extract_echo_ids_matches_only_top_level_snake_case_ids():
    payload = {
        "id": 7,
        "request_id": "req-1",
        "tenant_id": "tenant-1",
        "requestId": "not-matched",
        "arguments": {"group_id": "business-id"},
        "nested": {"cause_id": "not-matched"},
    }
    assert extract_echo_ids(payload) == {
        "id": 7,
        "request_id": "req-1",
        "tenant_id": "tenant-1",
    }


def test_flat_request_keeps_agent_ids_out_of_arguments():
    request = ToolInvokeRequest.model_validate({
        "request_id": "req-1",
        "session_id": "session-1",
        "brand": "丰田",
        "model": "汉兰达",
    })
    assert request.arguments == {"brand": "丰田", "model": "汉兰达"}
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run the test command with:

```powershell
Invoke-RoxiePytest -q -p no:cacheprovider tests/test_invoke_echo_request.py
```

Expected: import failures for the missing echo helper/context or assertions showing IDs remain in flat `arguments`.

- [ ] **Step 3: Implement the minimal extraction helpers and request validator**

Add to `app/core/responses.py`:

```python
EchoValue = str | int
echo_ctx: ContextVar[dict[str, EchoValue]] = ContextVar("echo", default={})


def is_echo_id_key(field_name: str) -> bool:
    return field_name == "id" or field_name.endswith("_id")


def extract_echo_ids(payload: object) -> dict[str, EchoValue]:
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if is_echo_id_key(key)
        and value is not None
        and not isinstance(value, bool)
        and isinstance(value, (str, int))
    }
```

Update `ToolInvokeRequest.merge_flat_payload` to validate every matching top-level ID, preserve matching ID fields as model extras, and exclude them when building flat `arguments`. A matching non-null value that is not a non-boolean `str | int` raises `ValueError`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same focused command. Expected: all Task 1 tests pass.

- [ ] **Step 5: Run the existing registry/slot tests**

Run the test command with:

```powershell
Invoke-RoxiePytest -q -p no:cacheprovider tests/test_invoke_echo_request.py tests/test_registry_slot_extraction.py
```

Expected: existing request and slot behavior remains green.

### Task 2: Echo on every invoke success and error response

**Files:**
- Modify: `app/main.py`
- Modify: `app/api/v1/schemas.py`
- Modify: `app/api/v1/endpoints/tools.py`
- Modify: `tests/test_success_response_envelope.py`
- Modify: `tests/test_error_response_envelope.py`
- Extend: `tests/test_invoke_echo_request.py`

**Interfaces:**
- Consumes: `echo_ctx` and `extract_echo_ids` from Task 1.
- Produces: `ToolInvokeResponse.echo: dict[str, str | int]`.
- Produces: invoke-specific standard handling for `RequestValidationError`.

- [ ] **Step 1: Write failing API tests for success, empty echo, platform errors, invalid IDs, and isolation**

Required literal assertions:

```python
assert response.json()["echo"] == {
    "request_id": "req-1",
    "session_id": "session-1",
    "tenant_id": "tenant-1",
    "task_id": 1001,
}
assert no_id_response.json()["echo"] == {}
assert error_response.json()["echo"] == {"request_id": "req-error"}
```

Also cover:

- `arguments.group_id` is not echoed;
- top-level `trace_id` is echoed but does not replace header-derived envelope `trace_id`;
- invalid top-level `session_id={}` returns HTTP 400, `code=40000`, and preserves other valid IDs in echo;
- malformed JSON returns HTTP 400, `code=40000`, and `echo={}`;
- two concurrent requests synchronized with a barrier return their own ID values without leakage;
- a non-invoke endpoint response has no echo field.

- [ ] **Step 2: Run focused API tests and verify RED**

Run the test command with:

```powershell
Invoke-RoxiePytest -q -p no:cacheprovider tests/test_invoke_echo_request.py tests/test_success_response_envelope.py tests/test_error_response_envelope.py
```

Expected: missing `echo`, default FastAPI 422 payloads, or context isolation assertions fail.

- [ ] **Step 3: Implement request-scoped echo context**

Extend the current trace middleware in `app/main.py`:

1. Match `POST` paths ending in `/invoke`.
2. Initialize `echo_ctx` to `{}` and save its token.
3. Attempt `await request.json()` and set valid IDs from `extract_echo_ids`.
4. Run `call_next`.
5. Reset both trace and echo tokens in `finally`.

Reading invalid JSON must not raise from middleware; the route validation handler owns that error response.

- [ ] **Step 4: Implement invoke response and error envelopes**

Add a required `echo` field to `ToolInvokeResponse` with a factory that copies the current echo context. Return `ToolInvokeResponse(data=result)` from the invoke endpoint.

For `ToolPlatformError` and unhandled exceptions, append the current echo only when the request is a `POST .../invoke`. Register a `RequestValidationError` handler that returns HTTP 400 with `code=40000`, `data=null`, the request trace, and echo for invoke routes; delegate non-invoke validation failures to FastAPI's standard handler.

- [ ] **Step 5: Run focused API tests and verify GREEN**

Run the Task 2 focused command from Step 2. Expected: all Task 2 tests pass, including concurrent isolation.

- [ ] **Step 6: Run all response and request tests**

Run the Task 2 focused command from Step 2. Expected: success and every covered error code retain `code/message/data/trace_id/echo`.

### Task 3: Schema-property projection for all eight tools

**Files:**
- Modify: `app/core/slot_extractor.py`
- Modify: `tests/test_registry_slot_extraction.py`
- Create: `tests/test_invoke_argument_filtering.py`

**Interfaces:**
- Consumes: `extract_slots(arguments, input_schema)`.
- Produces: for schemas without `x-extract`, a shallow projection containing only keys declared by `input_schema.properties`.

- [ ] **Step 1: Write failing projection tests**

```python
def test_schema_without_x_extract_drops_unknown_agent_fields():
    schema = {
        "type": "object",
        "properties": {"brand": {"type": "string"}, "model": {"type": "string"}},
    }
    assert extract_slots(
        {"brand": "丰田", "model": "汉兰达", "request_id": "req-1", "agent_state": {}},
        schema,
    ) == {"brand": "丰田", "model": "汉兰达"}
```

Add a registry-level test proving an existing non-`x-extract` tool handler receives declared fields only.

- [ ] **Step 2: Run focused projection tests and verify RED**

Run the test command with:

```powershell
Invoke-RoxiePytest -q -p no:cacheprovider tests/test_invoke_argument_filtering.py tests/test_registry_slot_extraction.py
```

Expected: current function returns the original arguments unchanged.

- [ ] **Step 3: Implement default property projection**

When `x-extract` is absent and `properties` is a dictionary, return only present keys declared in `properties`. Preserve the old pass-through only for schemas that do not define object properties.

- [ ] **Step 4: Run focused projection and all registry tests**

Run the Task 3 focused command from Step 2. Expected: new default projection and existing nested five-tool extraction both pass.

### Task 4: OpenAPI, integration examples, and regression verification

**Files:**
- Modify: `app/api/v1/endpoints/tools.py`
- Modify: `app/api/v1/schemas.py`
- Modify: `examples/orchestrator/*.json`
- Modify: `examples/orchestrator/README.md`
- Modify: `README.md`
- Modify: `tests/test_orchestrator_examples.py`

**Interfaces:**
- Produces: directly usable orchestration request examples with multiple top-level IDs.

- [ ] **Step 1: Add or update example behavior tests**

Tests must load each example, verify that it contains representative top-level `request_id` and `session_id`, validate only `request["arguments"]` against the Tool input schema, and ensure ID fields are outside `arguments`.

- [ ] **Step 2: Run example tests and verify RED**

Run the test command with:

```powershell
Invoke-RoxiePytest -q -p no:cacheprovider tests/test_orchestrator_examples.py
```

Expected: current examples do not contain the required IDs.

- [ ] **Step 3: Update examples and documentation**

Add representative `request_id`, `session_id`, `tenant_id`, and `task_id` values to orchestration examples. Update the documented response to include echo and explain top-level `id`/`*_id`, nested-ID exclusion, and empty `{}` behavior.

- [ ] **Step 4: Run focused tests and the full suite**

Run the focused example command, then run the full suite with:

```powershell
Invoke-RoxiePytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

- [ ] **Step 5: Run compile and contract verification**

Run Python `compileall`, `git diff --check`, and `verify_rag_runtime_contracts.py` against `http://172.16.67.169:8000`.

Expected: compilation succeeds, no whitespace errors, all five schemas match RAG 0.7.0, and all five RAG endpoints return HTTP 200.

- [ ] **Step 6: Review and commit implementation**

Stage only scoped implementation, tests, documentation, and examples. Confirm `.workbuddy/` remains untracked. Commit with:

```text
feat: echo agent ids in tool invoke responses
```
