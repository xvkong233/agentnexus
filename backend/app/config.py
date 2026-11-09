"""应用配置：全部来自环境变量 / .env 文件。"""
import base64
import hashlib
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AgentNexus · 灵枢"

    # 安全
    secret_key: str = "dev-secret-key"
    master_key: str = ""
    access_token_expire_hours: int = 12

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./dev.db"

    # 智谱 Managed Agents 上游
    bigmodel_mock: bool = True
    bigmodel_base_url: str = "https://agent-api.bigmodel.cn/api/agent/managed"
    bigmodel_channel_base_url: str = "https://agent-api.bigmodel.cn/api/agent/forward/v0"
    zai_version: str = "2026-05-26"
    zai_beta: str = "managed-agents-2026-09-22"
    http_timeout_seconds: float = 60.0

    # 初始管理员
    first_admin_user: str = "admin"
    first_admin_password: str = "admin123456"

    # 后台任务
    worker_enabled: bool = True
    metering_interval_seconds: int = 30
    sync_interval_seconds: int = 60
    guard_interval_seconds: int = 60

    @property
    def fernet_key(self) -> bytes:
        """由 MASTER_KEY（或退化为 SECRET_KEY）派生 Fernet 32 字节密钥。"""
        material = (self.master_key or self.secret_key or "fallback").encode("utf-8")
        digest = hashlib.sha256(material).digest()
        return base64.urlsafe_b64encode(digest)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
