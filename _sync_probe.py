"""一次性脚本：从 Nacos 发现 rag 服务实例并抓取其 OpenAPI 契约。"""
import asyncio
import json
import sys

import httpx
from v2.nacos import ListInstanceParam, NacosNamingService

from app.config import get_settings
from app.core.nacos import build_client_config


async def main() -> None:
    s = get_settings()
    naming = await NacosNamingService.create_naming_service(build_client_config(s))
    try:
        for service_name, tag in ((s.rag_service_name, "rag-service"),):
            instances = await naming.list_instances(
                ListInstanceParam(
                    service_name=service_name,
                    group_name=s.nacos_group,
                    healthy_only=True,
                )
            )
            fresh = [(i.ip, i.port) for i in instances if i.healthy and i.enabled]
            print(f"[{tag}] {service_name} -> {fresh}", flush=True)
            if not fresh:
                continue
            ip, port = fresh[0]
            url = f"http://{ip}:{port}/openapi.json"
            try:
                resp = httpx.get(url, timeout=15)
                resp.raise_for_status()
                out = f"_openapi_{tag}.json"
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(resp.json(), f, ensure_ascii=False, indent=2)
                print(f"[{tag}] openapi saved -> {out}", flush=True)
            except Exception as exc:
                print(f"[{tag}] fetch openapi failed: {exc}", flush=True)
    finally:
        await naming.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
