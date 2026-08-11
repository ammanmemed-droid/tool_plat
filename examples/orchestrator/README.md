# 编排层五工具联调示例（RAG 0.7.0）

统一调用地址：

```text
POST /api/v1/tools/{tool_name}/invoke
Content-Type: application/json
```

Context、Grouping 使用 full scan 示例；Cause、Diagnostic、Repair 使用 Grouping 返回的一个完整
`groups[].dtc_codes`。五个请求文件均可直接作为请求体。

请求体顶层字段名为 `id` 或以 `_id` 结尾的字符串/整数会原样回显到 `echo`，但不会进入
Tool 参数或转发给 RAG。只扫描顶层，`arguments` 内的业务 ID 不回显。

示例：

```bash
curl -X POST http://localhost:8000/api/v1/tools/dtc_grouping_service/invoke \
  -H "Content-Type: application/json" \
  -H "X-Trace-ID: orchestration-demo-001" \
  --data-binary @examples/orchestrator/dtc_grouping_invoke.json
```

成功响应统一为：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "groups": [],
    "standalone_dtcs": [],
    "issues": [],
    "meta": null,
    "uncertainty_note": null,
    "missing_required_info": null
  },
  "trace_id": "orchestration-demo-001",
  "echo": {
    "request_id": "orchestration-dtc_grouping_service-001",
    "session_id": "repair-session-001",
    "tenant_id": "tenant-demo",
    "task_id": 1001
  }
}
```

RAG 返回的完整业务对象位于 `data`，不会再嵌套一层业务信封。
未提交任何匹配 ID 时，invoke 响应仍包含 `"echo": {}`。成功和错误响应使用相同回显规则。
