"""上游服务发现：基于 Nacos 的实时实例查询（不缓存实例）。

- 支持从 Nacos 发现上游服务（roxie-supper-rag-service），
  客户端通过 watch() 声明需要发现的服务名；
- 不维护任何实例缓存：工具 handler 每次调用 pick_instance 时
  都通过 run_coroutine_threadsafe 在主事件循环上实时向 Nacos 查询，
  保证永远拿到当前最新的健康实例列表（实例被删除/替换后立即可见）；
- 配置 rag_base_url 直连地址时跳过 Nacos 发现（联调/应急通道）。
"""
import asyncio
import logging
import random
import threading

from v2.nacos import ListInstanceParam, NacosNamingService

from app.config import get_settings

logger = logging.getLogger(__name__)


class RagServiceDiscovery:
    """多上游服务实例实时发现（无缓存）。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._naming_service: NacosNamingService | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watched: set[str] = set()
        self._lock = threading.Lock()

    @property
    def direct_url(self) -> str:
        """配置的直连地址；为空表示走 Nacos 发现。"""
        return self._settings.rag_base_url.rstrip("/")

    def attach(self, naming_service: NacosNamingService | None) -> None:
        self._naming_service = naming_service

    def watch(self, *service_names: str) -> None:
        """声明需要发现的上游服务（客户端初始化时调用）。"""
        with self._lock:
            self._watched.update(service_names)

    # ---------- 生命周期（主事件循环内调用） ----------

    async def start(self) -> None:
        """捕获主事件循环，供同步 handler 线程实时查询 Nacos。"""
        if self.direct_url:
            logger.info("上游服务使用直连地址: %s（跳过 Nacos 发现）", self.direct_url)
            return
        if self._naming_service is None:
            logger.warning("Nacos naming service 不可用，上游服务发现未启动")
            return
        self._loop = asyncio.get_running_loop()
        logger.info("上游服务发现已启动（实时查询，无实例缓存）: services=%s", sorted(self._watched))

    async def stop(self) -> None:
        self._loop = None

    # ---------- 选取（同步，线程安全；每次实时查询 Nacos，不缓存） ----------

    def pick_instance(self, service_name: str) -> tuple[str, int] | None:
        """实时从 Nacos 查询健康实例并随机挑选；无可用实例返回 None。"""
        naming = self._naming_service
        loop = self._loop
        if naming is None or loop is None:
            return None
        try:
            future = asyncio.run_coroutine_threadsafe(
                naming.list_instances(
                    ListInstanceParam(
                        service_name=service_name,
                        group_name=self._settings.nacos_group,
                        healthy_only=True,
                    )
                ),
                loop,
            )
            instances = future.result(timeout=self._settings.rag_discovery_query_timeout)
        except Exception:
            logger.exception("上游实例实时查询失败: %s", service_name)
            return None
        healthy = [(i.ip, i.port) for i in instances if i.healthy and i.enabled]
        if not healthy:
            return None
        return random.choice(healthy)


# 全局单例
rag_discovery = RagServiceDiscovery()
