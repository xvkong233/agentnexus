"""FastAPI 依赖：数据库会话与三端鉴权（admin JWT / portal JWT / open API Key）。"""
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PlatformError
from app.core.security import decode_token, hash_api_key
from app.db import get_db
from app.models import Admin, Tenant, TenantApiKey, TenantUser

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise PlatformError(401, "unauthorized", "缺少访问令牌")
    return auth[7:].strip()


def _payload(request: Request) -> dict:
    try:
        return decode_token(_bearer_token(request))
    except PlatformError:
        raise
    except Exception:
        raise PlatformError(401, "unauthorized", "访问令牌无效或已过期")


async def require_admin(request: Request, db: DbSession) -> Admin:
    payload = _payload(request)
    if payload.get("role") != "admin":
        raise PlatformError(403, "forbidden", "需要管理员权限")
    admin = await db.get(Admin, payload["sub"])
    if not admin:
        raise PlatformError(401, "unauthorized", "管理员不存在")
    request.state.actor = ("admin", admin.id, admin.username)
    return admin


async def require_tenant_user(request: Request, db: DbSession) -> TenantUser:
    payload = _payload(request)
    if payload.get("role") != "tenant":
        raise PlatformError(403, "forbidden", "需要客户门户权限")
    user = await db.get(TenantUser, payload["sub"])
    if not user or user.status != "active":
        raise PlatformError(401, "unauthorized", "账号不可用")
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or tenant.status != "active":
        raise PlatformError(403, "forbidden", "租户已被停用")
    request.state.actor = ("tenant", user.id, user.username)
    request.state.tenant_id = user.tenant_id
    return user


async def require_open_api_key(
    request: Request,
    db: DbSession,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> TenantApiKey:
    raw = x_api_key
    if not raw and authorization and authorization.startswith("Bearer "):
        raw = authorization[7:].strip()
    if not raw:
        raise PlatformError(401, "unauthorized", "缺少 API Key（请求头 X-API-Key）")
    stmt = select(TenantApiKey).where(TenantApiKey.key_hash == hash_api_key(raw))
    key = (await db.execute(stmt)).scalar_one_or_none()
    if not key or key.status != "active":
        raise PlatformError(401, "unauthorized", "API Key 无效或已停用")
    tenant = await db.get(Tenant, key.tenant_id)
    if not tenant or tenant.status != "active":
        raise PlatformError(403, "forbidden", "租户已被停用")
    request.state.actor = ("tenant_api", key.id, key.prefix)
    request.state.tenant_id = key.tenant_id
    request.state.api_key_id = key.id
    from app.models import utcnow

    key.last_used_at = utcnow()
    await db.commit()
    return key
