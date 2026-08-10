"""Nacos 服务注册与注销（nacos-sdk-python gRPC 协议）。

本平台 Nacos 仅开放 gRPC 端口（主端口 + port_offset，默认 9848），
使用官方 nacos-sdk-python 通过 gRPC 长连接注册临时实例并自动保活。

服务启动时把自身注册为 Nacos 实例，Agent 可通过 Nacos 按
service-name 发现本中台地址，再调用 /api/v1/tools 完成工具发现。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path

from v2.nacos import (
    ClientConfigBuilder,
    DeregisterInstanceParam,
    GRPCConfig,
    NacosNamingService,
    RegisterInstanceParam,
)

from app.config import Settings

logger = logging.getLogger(__name__)

_SDK_LOG_DIR = str(Path(".nacos") / "logs")
_SDK_CACHE_DIR = str(Path(".nacos") / "cache")
_CREATE_TIMEOUT_S = 20.0
_REGISTER_TIMEOUT_S = 10.0
_SHUTDOWN_TIMEOUT_S = 10.0


class _DropSdkReconnectSpam(logging.Filter):
    """丢弃 nacos-sdk 重连刷屏日志（failed to connect nacos server）。"""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        try:
            return "failed to connect nacos server" not in record.getMessage()
        except Exception:  # noqa: BLE001
            return True


_SDK_FILTER_INSTALLED = False


def detect_local_ip(server_addr: str) -> str:
    """通过向 Nacos 地址建立 UDP 连接探测本机出口 IP。"""
    host = (server_addr or "").split(":")[0].strip() or "8.8.8.8"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((host, 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def build_client_config(settings: Settings):
    """构造 nacos-sdk ClientConfig（gRPC 端口 = 主端口 + port_offset）。"""
    builder = (
        ClientConfigBuilder()
        .server_address(settings.nacos_server_addr)
        .namespace_id(settings.nacos_namespace)
        .grpc_config(GRPCConfig(port_offset=settings.nacos_grpc_port_offset))
        .timeout_ms(5000)
        .heart_beat_interval(settings.nacos_heartbeat_interval * 1000)
        .log_level("WARNING")
        .log_dir(_SDK_LOG_DIR)
        .cache_dir(_SDK_CACHE_DIR)
    )
    if settings.nacos_username:
        builder = builder.username(settings.nacos_username).password(settings.nacos_password)
    return builder.build()


def _install_sdk_log_filter() -> None:
    global _SDK_FILTER_INSTALLED
    if _SDK_FILTER_INSTALLED:
        return
    root = logging.getLogger()
    if not any(isinstance(f, _DropSdkReconnectSpam) for f in root.filters):
        root.addFilter(_DropSdkReconnectSpam())
    _SDK_FILTER_INSTALLED = True


def _patch_sdk_async_close() -> None:
    """修复 SDK 在能力协商失败时未 await close 协程的问题。"""
    from v2.nacos.transport.rec_ability_context import RecAbilityContext

    if getattr(RecAbilityContext, "_roxie_async_close_patched", False):
        return

    def check(self, connection) -> bool:
        if connection.is_abilities_set():
            return True
        self.logger.error(
            "Client don't receive server abilities table even empty table "
            "but server supports ability negotiation. "
            "You can check if it is need to adjust the timeout of ability "
            "negotiation if always fail to connect."
        )
        connection.set_abandon(True)
        result = connection.close()
        if inspect.isawaitable(result):
            asyncio.create_task(result)
        return False

    RecAbilityContext.check = check
    RecAbilityContext._roxie_async_close_patched = True


class NacosRegistrar:
    """封装 gRPC 注册、断线重连与注销生命周期。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._naming_service: NacosNamingService | None = None
        self._lifecycle_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._registered = False
        self._on_naming_ready: Callable[[NacosNamingService], Awaitable[None]] | None = None
        self.service_ip = settings.service_ip or detect_local_ip(settings.nacos_server_addr)
        self.service_port = settings.port
        self.service_name = settings.app_name

    @property
    def enabled(self) -> bool:
        return self._settings.nacos_enabled

    @property
    def naming_service(self) -> NacosNamingService | None:
        """供服务发现复用的 naming service（与注册共用同一条 gRPC 长连接）。"""
        return self._naming_service

    def set_on_naming_ready(
        self, callback: Callable[[NacosNamingService], Awaitable[None]]
    ) -> None:
        """注册回调：naming service 首次创建成功后触发（含失败补偿场景）。"""
        self._on_naming_ready = callback

    # ---------- 生命周期 ----------

    async def register(self) -> None:
        """启动后台 gRPC 连接并注册实例；注册中心不可达不阻断服务启动。"""
        if not self.enabled:
            logger.info("Nacos 注册已禁用（nacos_enabled=false）")
            return
        _install_sdk_log_filter()
        _patch_sdk_async_close()
        self._stop_event = asyncio.Event()
        self._lifecycle_task = asyncio.create_task(self._async_main(), name="nacos-lifecycle")

    async def deregister(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        task = self._lifecycle_task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=_CREATE_TIMEOUT_S + _REGISTER_TIMEOUT_S + 5)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            self._lifecycle_task = None
        self._registered = False
        self._naming_service = None

    # ---------- 内部实现 ----------

    async def _async_main(self) -> None:
        """持续执行「连接注册 → 保活」，失败后定时重试直至停止。"""
        assert self._stop_event is not None
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            naming = None
            try:
                naming = await self._create_and_register()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._registered = False
                self._naming_service = None
                if attempt == 1:
                    logger.exception(
                        "Nacos 注册失败，服务将继续以未注册状态运行（后台将持续重试）: server=%s",
                        self._settings.nacos_server_addr,
                    )
                else:
                    logger.warning("Nacos 第 %d 次注册仍失败，将继续重试", attempt)
                if await self._wait_stop_or_retry():
                    break
                continue

            self._naming_service = naming
            self._registered = True
            if attempt > 1:
                logger.info(
                    "Nacos 后台自愈注册成功: service=%s instance=%s:%s attempt=%d",
                    self.service_name,
                    self.service_ip,
                    self.service_port,
                    attempt,
                )
            if self._on_naming_ready is not None:
                await self._on_naming_ready(naming)
            await self._stop_event.wait()
            try:
                await self._shutdown_naming(naming, deregister=True)
            finally:
                self._registered = False
                self._naming_service = None
            break

    async def _wait_stop_or_retry(self) -> bool:
        """等待停止信号或重试间隔；返回 True 表示应停止。"""
        assert self._stop_event is not None
        delay = max(0.1, float(self._settings.nacos_retry_interval))
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            return True
        except TimeoutError:
            return False

    async def _create_and_register(self) -> NacosNamingService:
        client_config = build_client_config(self._settings)
        naming = await asyncio.wait_for(
            NacosNamingService.create_naming_service(client_config),
            timeout=_CREATE_TIMEOUT_S,
        )
        try:
            ok = await asyncio.wait_for(
                naming.register_instance(self._register_param()),
                timeout=_REGISTER_TIMEOUT_S,
            )
        except Exception:
            await self._shutdown_naming(naming, deregister=False)
            raise
        if ok is not True:
            await self._shutdown_naming(naming, deregister=False)
            raise RuntimeError("Nacos register_instance returned false")
        logger.info(
            "已注册到 Nacos: service=%s, instance=%s:%s, namespace=%s, grpc_offset=%d",
            self.service_name,
            self.service_ip,
            self.service_port,
            self._settings.nacos_namespace,
            self._settings.nacos_grpc_port_offset,
        )
        return naming

    async def _shutdown_naming(self, naming: NacosNamingService | None, *, deregister: bool) -> None:
        if naming is None:
            return
        s = self._settings
        if deregister:
            try:
                await asyncio.wait_for(
                    naming.deregister_instance(
                        DeregisterInstanceParam(
                            service_name=self.service_name,
                            group_name=s.nacos_group,
                            ip=self.service_ip,
                            port=self.service_port,
                            cluster_name=s.nacos_cluster,
                            ephemeral=True,
                        )
                    ),
                    timeout=_REGISTER_TIMEOUT_S,
                )
                logger.info(
                    "已从 Nacos 注销: %s@%s:%s",
                    self.service_name,
                    self.service_ip,
                    self.service_port,
                )
            except Exception:
                logger.warning("Nacos 注销失败", exc_info=True)
        try:
            await asyncio.wait_for(naming.shutdown(), timeout=_SHUTDOWN_TIMEOUT_S)
        except Exception:
            logger.debug("Nacos shutdown 出错", exc_info=True)

    def _register_param(self) -> RegisterInstanceParam:
        s = self._settings
        return RegisterInstanceParam(
            service_name=self.service_name,
            group_name=s.nacos_group,
            ip=self.service_ip,
            port=self.service_port,
            cluster_name=s.nacos_cluster,
            ephemeral=True,
            healthy=True,
            enabled=True,
            weight=1.0,
            metadata={
                "version": s.app_version,
                "framework": "fastapi",
                "tool_discovery_path": "/api/v1/tools",
                "health_path": "/api/v1/health",
            },
        )
