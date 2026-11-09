"""平台上游 BigModel API Key 管理（加密落库，仅回显前缀）。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.crypto import encrypt_secret
from app.core.deps import DbSession, require_admin
from app.core.errors import bad_request, not_found
from app.models import PlatformKey
from app.services.audit import write_audit

router = APIRouter(dependencies=[Depends(require_admin)])


class CreateKeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=8)
    tenant_id: str | None = None  # 绑定租户（上游费用归属）
    is_default: bool = False


def _view(k: PlatformKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "key_hint": k.key_hint,
        "tenant_id": k.tenant_id,
        "is_default": k.is_default,
        "status": k.status,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }


@router.get("/platform-keys")
async def list_keys(db: DbSession):
    keys = (await db.execute(select(PlatformKey).order_by(PlatformKey.created_at.desc()))).scalars().all()
    return {"items": [_view(k) for k in keys]}


@router.post("/platform-keys")
async def create_key(body: CreateKeyBody, request: Request, db: DbSession):
    if body.is_default:
        await db.execute(update(PlatformKey).values(is_default=False))
    key = PlatformKey(
        name=body.name,
        encrypted_key=encrypt_secret(body.api_key.strip()),
        key_hint="…" + body.api_key.strip()[-4:],
        tenant_id=body.tenant_id,
        is_default=body.is_default,
    )
    db.add(key)
    await db.flush()
    if not body.is_default:
        any_default = (
            await db.execute(select(PlatformKey).where(PlatformKey.is_default.is_(True)).limit(1))
        ).scalar_one_or_none()
        if not any_default:
            key.is_default = True
    await write_audit(db, request, "platform_key.create", "platform_key", key.id, {"name": body.name})
    await db.commit()
    return _view(key)


@router.post("/platform-keys/{key_id}/set-default")
async def set_default(key_id: str, request: Request, db: DbSession):
    key = await db.get(PlatformKey, key_id)
    if not key:
        raise not_found("密钥不存在")
    await db.execute(update(PlatformKey).values(is_default=False))
    key.is_default = True
    await write_audit(db, request, "platform_key.set_default", "platform_key", key.id)
    await db.commit()
    return _view(key)


@router.post("/platform-keys/{key_id}/status")
async def set_status(key_id: str, status: str, request: Request, db: DbSession):
    key = await db.get(PlatformKey, key_id)
    if not key:
        raise not_found("密钥不存在")
    if status not in ("active", "disabled"):
        raise bad_request("status 仅支持 active/disabled")
    if key.is_default and status == "disabled":
        raise bad_request("默认密钥不可停用，请先将其他密钥设为默认")
    key.status = status
    await write_audit(db, request, "platform_key.status", "platform_key", key.id, {"status": status})
    await db.commit()
    return _view(key)
