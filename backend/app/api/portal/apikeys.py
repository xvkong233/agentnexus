"""客户开放平台 API Key 管理。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import not_found
from app.core.security import generate_api_key
from app.models import TenantApiKey
from app.services.audit import write_audit

router = APIRouter(dependencies=[Depends(require_tenant_user)])


class CreateBody(BaseModel):
    name: str = "default"


@router.get("/api-keys")
async def list_keys(request: Request, db: DbSession):
    keys = (
        await db.execute(
            select(TenantApiKey)
            .where(TenantApiKey.tenant_id == request.state.tenant_id)
            .order_by(TenantApiKey.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": k.id, "name": k.name, "prefix": k.prefix + "…", "status": k.status,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ]
    }


@router.post("/api-keys")
async def create_key(body: CreateBody, request: Request, db: DbSession):
    full, prefix, key_hash = generate_api_key("ak")
    key = TenantApiKey(tenant_id=request.state.tenant_id, name=body.name[:128], prefix=prefix, key_hash=key_hash)
    db.add(key)
    await write_audit(db, request, "api_key.create", "tenant_api_key", key.id, {"name": body.name})
    await db.commit()
    return {"id": key.id, "name": key.name, "prefix": prefix + "…", "api_key": full}


@router.post("/api-keys/{key_id}/revoke")
async def revoke_key(key_id: str, request: Request, db: DbSession):
    key = await db.get(TenantApiKey, key_id)
    if not key or key.tenant_id != request.state.tenant_id:
        raise not_found("API Key 不存在")
    key.status = "revoked"
    await write_audit(db, request, "api_key.revoke", "tenant_api_key", key.id)
    await db.commit()
    return {"ok": True}
