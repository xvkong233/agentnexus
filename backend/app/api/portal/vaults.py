"""客户凭据保管库（Vaults）：MCP / OAuth / 环境变量密钥，只写不读。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import not_found
from app.models import Vault
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_tenant_user)])


def _tenant_id(request) -> str:
    return request.state.tenant_id


async def _own(db, request, vault_id: str) -> Vault:
    row = await db.get(Vault, vault_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("保管库不存在")
    return row


class VaultBody(BaseModel):
    display_name: str
    metadata: dict | None = None


class CredentialBody(BaseModel):
    name: str
    auth: dict  # {"type": "static_bearer"/"bearer"/"mcp_oauth"/"oauth"/"environment_variable", ...}


class CredentialPatchBody(BaseModel):
    auth: dict | None = None
    name: str | None = None


def _view(v: Vault) -> dict:
    return {
        "id": v.id,
        "upstream_id": v.upstream_id,
        "display_name": v.name,
        "status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.get("/vaults")
async def list_vaults(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Vault).where(Vault.tenant_id == _tenant_id(request)).order_by(Vault.created_at.desc())
        )
    ).scalars().all()
    return {"items": [_view(v) for v in rows]}


@router.post("/vaults")
async def create_vault(body: VaultBody, request: Request, db: DbSession):
    client = await get_client_for_tenant(db, _tenant_id(request))
    payload: dict = {"display_name": body.display_name[:255]}
    if body.metadata:
        payload["metadata"] = body.metadata
    up = await client.create_vault(payload)
    row = Vault(tenant_id=_tenant_id(request), upstream_id=up["id"], name=up.get("display_name") or body.display_name)
    db.add(row)
    await db.commit()
    return _view(row)


@router.post("/vaults/{vault_id}/archive")
async def archive_vault(vault_id: str, request: Request, db: DbSession):
    row = await _own(db, request, vault_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.archive_vault(row.upstream_id)
    row.status = "archived"
    await db.commit()
    return {"ok": True}


@router.get("/vaults/{vault_id}/credentials")
async def list_credentials(vault_id: str, request: Request, db: DbSession):
    row = await _own(db, request, vault_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.list_credentials(row.upstream_id, {"limit": 100})


@router.post("/vaults/{vault_id}/credentials")
async def add_credential(vault_id: str, body: CredentialBody, request: Request, db: DbSession):
    row = await _own(db, request, vault_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.add_credential(row.upstream_id, body.model_dump(exclude_none=True))


@router.post("/vaults/{vault_id}/credentials/{credential_id}")
async def update_credential(vault_id: str, credential_id: str, body: CredentialPatchBody, request: Request, db: DbSession):
    """轮换凭据：提交 auth 则替换，省略则保留。"""
    row = await _own(db, request, vault_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    payload: dict = {}
    if body.auth:
        payload["auth"] = body.auth
    if body.name:
        payload["name"] = body.name
    return await client.update_credential(row.upstream_id, credential_id, payload)


@router.delete("/vaults/{vault_id}/credentials/{credential_id}")
async def delete_credential(vault_id: str, credential_id: str, request: Request, db: DbSession):
    row = await _own(db, request, vault_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.delete_credential(row.upstream_id, credential_id)
