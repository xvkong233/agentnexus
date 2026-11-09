"""客户端工厂：按租户选择上游 API Key（绑定 Key > 平台默认 Key），Mock 模式统一返回模拟客户端。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_secret
from app.models import PlatformKey
from app.services.bigmodel.mock import MockBigModelClient
from app.services.bigmodel.real import RealBigModelClient

# Mock 单例：整个进程共享一个模拟上游
_mock_client = MockBigModelClient()


async def _select_key(db: AsyncSession, tenant_id: str | None) -> tuple[str, str]:
    """返回 (key_id, decrypted_api_key)。优先租户绑定 Key，其次默认 Key。"""
    if tenant_id:
        stmt = (
            select(PlatformKey)
            .where(PlatformKey.tenant_id == tenant_id, PlatformKey.status == "active")
            .limit(1)
        )
        key = (await db.execute(stmt)).scalar_one_or_none()
        if key:
            return key.id, decrypt_secret(key.encrypted_key)
    stmt = (
        select(PlatformKey)
        .where(PlatformKey.is_default.is_(True), PlatformKey.status == "active")
        .limit(1)
    )
    key = (await db.execute(stmt)).scalar_one_or_none()
    if key:
        return key.id, decrypt_secret(key.encrypted_key)
    raise RuntimeError("未配置可用的平台 API Key，请在管理端「平台密钥」中添加并设为默认")


async def get_client_for_tenant(db: AsyncSession, tenant_id: str | None):
    if settings.bigmodel_mock:
        return _mock_client
    _, api_key = await _select_key(db, tenant_id)
    return RealBigModelClient(api_key)


async def get_default_client(db: AsyncSession):
    """平台级调用（全局同步任务等），使用默认 Key。"""
    if settings.bigmodel_mock:
        return _mock_client
    _, api_key = await _select_key(db, None)
    return RealBigModelClient(api_key)


async def has_any_key(db: AsyncSession) -> bool:
    stmt = select(PlatformKey.id).where(PlatformKey.status == "active").limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None
