"""上游远程服务调用客户端（roxie-rag-service）。

每个工具调用：从 Nacos 发现缓存挑选实例 -> POST 到对应端点 -> 解析响应并返回业务结果。

响应兼容两种形态：
1. 裸业务结果 JSON（直接返回）；
2. 与本中台一致的信封 {code, message, data}（code=0 时解包 data）。
"""
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.core.discovery import rag_discovery
from app.core.exceptions import ToolExecutionError, ToolPlatformError
from app.core.logging_config import _truncate_utf8, get_app_logger
from app.core.responses import trace_id_ctx

logger = get_app_logger(__name__)


class RagServiceClient:
    """对上游远程服务的同步 HTTP 调用（handler 运行于线程池）。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = httpx.Client(
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        # 声明需要发现的上游服务
        rag_discovery.watch(self._settings.rag_service_name)

    def _candidate_urls(self, service_name: str, base_path: str, path: str) -> list[str]:
        """按优先级给出候选 URL：直连地址 > Nacos 发现实例。"""
        if rag_discovery.direct_url:
            return [f"{rag_discovery.direct_url}{base_path}/{path}"]
        instance = rag_discovery.pick_instance(service_name)
        if instance is None:
            return []
        ip, port = instance
        return [f"http://{ip}:{port}{base_path}/{path}"]

    @staticmethod
    def _serialize_log_body(value: object, max_bytes: int) -> str | None:
        """把请求参数 / 响应体序列化为单行日志字符串，超限截断；失败不影响业务调用。"""
        try:
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return None
        body, _truncated = _truncate_utf8(serialized, max(1, int(max_bytes)))
        return body

    def invoke(
        self,
        tool_name: str,
        path: str,
        arguments: dict[str, Any],
        *,
        service_name: str | None = None,
        base_path: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """统一远程调用。

        :param tool_name: 本中台工具名（用于错误信息与日志）
        :param path: 端点相对路径（如 dtc-context、diagnoses）
        :param arguments: 请求体（工具入参原样透传）
        :param service_name: 上游 Nacos 服务名，默认 roxie-rag-service
        :param base_path: 端点路径前缀，默认 /api/v1/tool-services
        :param timeout: 单次调用超时（秒），默认 rag_timeout
        """
        service = service_name or self._settings.rag_service_name
        prefix = base_path if base_path is not None else self._settings.rag_base_path
        req_timeout = timeout if timeout is not None else self._settings.rag_timeout

        urls = self._candidate_urls(service, prefix, path)
        if not urls:
            raise ToolExecutionError(
                tool_name,
                f"{service} 无可用健康实例（Nacos 服务名: {service}），请确认该服务已启动并注册",
            )

        last_error: str = ""
        for url in urls:
            try:
                trace_id = trace_id_ctx.get()
                headers = {"X-Trace-ID": trace_id} if trace_id else {}
                logger.info(
                    "发送RAG请求",
                    extra={
                        "event": "rag.request",
                        "tool_name": tool_name,
                        "http_path": path,
                        "rag_request_body": self._serialize_log_body(
                            arguments, self._settings.log_request_body_max_bytes
                        ),
                    },
                )
                resp = self._client.post(url, json=arguments, timeout=req_timeout, headers=headers)
                resp.raise_for_status()
                body = resp.json()
                logger.info(
                    "收到RAG响应",
                    extra={
                        "event": "rag.response",
                        "tool_name": tool_name,
                        "http_path": path,
                        "rag_response_body": self._serialize_log_body(
                            body, self._settings.log_request_body_max_bytes
                        ),
                    },
                )
                return self._unwrap(tool_name, service, body)
            except (httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                raise ToolPlatformError(
                    f"{service} 调用超时: {exc}",
                    code=50400,
                ) from exc
            except httpx.ConnectError as exc:
                # 实例不做缓存，下次调用会重新向 Nacos 实时查询，无需剔除标记；
                # 不在此打印 URL 与异常正文，最终只由请求完成摘要记录 error_type 与业务码
                last_error = f"请求 {url} 失败: {exc}"
                continue
            except httpx.HTTPStatusError as exc:
                upstream_codes = {502: 50200, 503: 50300, 504: 50400}
                upstream_code = upstream_codes.get(exc.response.status_code)
                if upstream_code is not None:
                    try:
                        body = exc.response.json()
                    except ValueError:
                        body = {}
                    detail = body.get("message") if isinstance(body, dict) else None
                    raise ToolPlatformError(
                        detail or f"{service} 返回 HTTP {exc.response.status_code}",
                        code=upstream_code,
                    ) from exc
                raise ToolExecutionError(
                    tool_name,
                    f"{service} 返回 HTTP {exc.response.status_code}: {exc.response.text[:300]}",
                ) from exc
            except ValueError as exc:
                raise ToolExecutionError(tool_name, f"{service} 响应不是合法 JSON: {exc}") from exc

        raise ToolExecutionError(tool_name, last_error or f"{service} 调用失败")

    @staticmethod
    def _unwrap(tool_name: str, service: str, body: object) -> dict[str, Any]:
        """兼容信封响应：code=0 时解包 data；否则原样返回。"""
        if isinstance(body, dict) and "code" in body and "data" in body:
            if body.get("code") == 0:
                data = body["data"]
                if not isinstance(data, dict):
                    raise ToolExecutionError(tool_name, f"{service} 响应 data 字段不是对象")
                return data
            raise ToolExecutionError(
                tool_name,
                f"{service} 业务错误 code={body.get('code')}: {body.get('message')}",
            )
        if not isinstance(body, dict):
            raise ToolExecutionError(tool_name, f"{service} 响应不是 JSON 对象")
        return body


# 全局单例
rag_client = RagServiceClient()
