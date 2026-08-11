"""应用配置：通过环境变量或 .env 文件覆盖默认值。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / "myskills"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 服务基础配置 ----
    app_name: str = "roxie-router-service"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    # 注册到 Nacos 的本机 IP；留空时自动探测
    service_ip: str = ""

    # ---- Nacos 注册中心配置 ----
    nacos_enabled: bool = True
    nacos_server_addr: str = "47.115.220.29:8848"
    nacos_namespace: str = "83060e12-9c80-4c8b-826c-c00705c52e29"
    nacos_username: str = "nacos"
    nacos_password: str = "Dev@nacos"
    nacos_group: str = "DEFAULT_GROUP"
    nacos_cluster: str = "DEFAULT"
    # 心跳间隔（秒）
    nacos_heartbeat_interval: int = 5
    # gRPC 端口偏移：命名协议连接 主端口 + offset（默认 8848 + 1000 = 9848）
    nacos_grpc_port_offset: int = 1000
    # 注册失败后的后台重试间隔（秒）
    nacos_retry_interval: float = 10.0

    # ---- roxie-rag-service 远程上游配置 ----
    # Nacos 中的服务名，工具调用经服务发现后转发到该服务
    rag_service_name: str = "roxie-supper-rag-service"
    # 远程工具服务路径前缀（dtc-context、cause-ranking 等）
    rag_base_path: str = "/api/v1/tool-services"
    # 综合诊断 / 原因卡片等接口路径前缀（diagnoses、dtc-cause-cards 等）
    diagnose_base_path: str = "/api/v1"
    # 直连地址（如 http://127.0.0.1:9100）；配置后跳过 Nacos 发现，用于联调/应急
    rag_base_url: str = ""
    # 普通工具调用超时（秒）
    rag_timeout: float = 15.0
    # 原因概率排序总预算为 45 秒，中台预留网络与响应解析余量
    cause_ranking_timeout: float = 50.0
    # 综合诊断 / 原因卡片调用超时（秒，含 LLM，耗时长于普通工具）
    diagnose_timeout: float = 60.0
    # 实例列表实时查询超时（秒，每次调用直接向 Nacos 查询，不做缓存）
    rag_discovery_query_timeout: float = 5.0

    # ---- 工具契约目录（tool-schema.json 所在目录） ----
    skills_dir: Path = SKILLS_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()
