"""客户门户认证与账户信息。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import PlatformError
from app.core.security import create_token, verify_password
from app.models import Tenant, TenantUser, Wallet

router = APIRouter()


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginBody, db: DbSession):
    user = (
        await db.execute(select(TenantUser).where(TenantUser.username == body.username))
    ).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise PlatformError(401, "invalid_credentials", "用户名或密码错误")
    if user.status != "active":
        raise PlatformError(403, "forbidden", "账号已被停用")
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or tenant.status != "active":
        raise PlatformError(403, "forbidden", "租户已被停用")
    token = create_token("tenant", user.id, tenant_id=user.tenant_id, name=user.username)
    return {
        "token": token,
        "user": {"id": user.id, "username": user.username, "display_name": user.display_name},
        "tenant": {"id": tenant.id, "name": tenant.name, "code": tenant.code},
    }


@router.get("/me")
async def me(request: Request, db: DbSession):
    user: TenantUser = await require_tenant_user(request, db)
    tenant = await db.get(Tenant, user.tenant_id)
    wallet = await db.get(Wallet, user.tenant_id)
    return {
        "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role},
        "tenant": {
            "id": tenant.id, "name": tenant.name, "code": tenant.code, "status": tenant.status,
            "low_balance_threshold": float(tenant.low_balance_threshold or 0),
        },
        "wallet": {
            "balance": float(wallet.balance) if wallet else 0,
            "blocked": bool(wallet.blocked) if wallet else False,
            "blocked_reason": wallet.blocked_reason if wallet else "",
        },
    }
